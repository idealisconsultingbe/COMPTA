from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from time import time
from odoo.addons.efficy_accounting.models.tools import Log
import logging
import json

_logger = logging.getLogger(__name__)


# class Query():
#
#     def __init__(self, key):
#         # todo: format docstrings
#         # params: list of dictionary params
#         self.key = key
#         self.payload = [{
#             '@name': 'api',
#             '@func': []
#         }]
#
#     def add_params(self, params_list):
#         self.payload[0]['@func'].append(
#             {'@name': 'query', 'key': self.key} | {p: params[p] for p in params} for params in params_list
#         )
#
#     def request(self):
#         self.dataset_raw = self.env['efficy.mapping.model'].json_request(self.payload)
#
#     def ans_format(self, mapping_dict):
#         # todo: format docstrings
#         """
#         {'entity': {
#             'fields': {'efficy_field': 'query_field'},
#             'relations' : {'entity': [query_fields]}
#         }}
#
#         'query_field': [
#             (entity, key_field, 'fields', 'efficy_field'),
#             (entity,
#
#         {'entity' : {
#             'key': {
#                 'fields': {'efficy_field': 'value', ...},
#                 'relations': {'entity': [keys]}
#             },
#             ...
#         }}
#         """
#         dic = {}
#         keys = []
#
#         for func in self.dataset_raw[0]['@func']:
#             for data in func['#result']['#data']:
#                 for d in data:
#                     mapping = mapping_dict[d]
#                     entity = mapping[0]
#                     key = data[mapping[1]]
#                     dic[entity][key]
#
#         return dic
#


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'efficy.integration.mixin']

    approbation_status = fields.Selection([('Approved', 'Approved'), ('Contested', 'Contested'), ('On Hold', 'On Hold')])
    efficy_attachment_ids = fields.One2many(comodel_name='efficy.invoice.attachment', inverse_name='move_id')
    amount_residual = fields.Monetary(store=True)
    efficy_reference = fields.Char()

    def sync_entity_one(self):

        def ans_format(ans):

            fields_document = ['K_DOCUMENT', 'R_F_INVOICE_STATUS', 'REFERENCE', 'COMMUNICATION', 'D_INVOICE', 'EXP_DATE', 'R_CURRCY', 'TOTAL_WITH_VAT', 'TOTAL_NO_VAT']

            dic = {}
            for func in ans[0]['@func']:
                for d in func['#result']['#data']:
                    dic |= {f: d.get(f) for f in fields_document if f in d}

            return [dic]


        self.ensure_one()

        payload = [{
            "@name": "consult",
            "entity": "Docu",
            "key": self.efficy_key,
            "@func": [
                {"@name": "master"},
                {"@name": "category", "category": "DOCU$INVOICING"},
            ]
        }]

        ans = self.env['efficy.mapping.model'].json_request(payload)
        sync_date = fields.Datetime.now()
        sync_sequence = self.env.ref('efficy_accounting.seq_efficy_sync_log').next_by_id()
        self = self.with_context(sync_date=sync_date, sync_sequence=sync_sequence)
        dic_document = ans_format(ans)
        self.process_data(dic_document, 'K_DOCUMENT', 'Docu')

    def name_get(self):
        return [(rec.id, rec.payment_reference) for rec in self]

    def _preprocess_data(self, d, log):

        if self and self.state not in ['draft']:
            log.skipped("Entry posted, skipping")

    def _process_data(self, d, log):

        def parse_reference(ref):

            # CHECK REFERENCE + SPLIT
            try:
                type, year, country = ref.split('-')[:3]
            except:
                log.skipped("Bad formatted reference: %s" % ref)

            # CHECK YEAR
            if int(year) < 2021:
                log.skipped("Skipped record from date %s : %s" % (year, ref))

            # CHECK COMPANY
            company_id = self.env['res.company'].search([('efficy_code', '=', country)])
            if not company_id:
                log.skipped("No company found with code %s for %s" % (country, ref))

            # SET MOVE TYPE
            move_type = 'entry'
            if type == 'INV':
                move_type = 'out_invoice'
            if type == 'IINV':
                move_type = 'in_invoice'
            if type == 'EXP':
                move_type = 'in_invoice'

            return move_type, company_id

        move_type, company_id = parse_reference(d['REFERENCE'])

        # SEARCH CURRENCY
        currency_id = self.env['res.currency'].search([('name', '=', d['R_CURRCY'])])

        if not currency_id:
            log.failed("No currency found for %s" % d['R_CURRCY'] or 'None')

        line_vals = [(5, 0, 0)] + [(0, 0, self.env['account.move.line']._process_data(data, log)) for data in self._context.get('line_data') if data['K_DOCUMENT'] == d['K_DOCUMENT']]

        partner_id = self.env['res.partner'].search([('efficy_entity', '=', 'Comp'), ('efficy_key', '=', d.get('K_COMPANY'))]) or\
                     self.env['res.partner'].create({'efficy_entity': 'Comp', 'efficy_key': d.get('K_COMPANY')})

        return {
            'efficy_key': d['K_DOCUMENT'],
            'efficy_entity': 'Docu',
            'approbation_status': d['R_F_INVOICE_STATUS'],
            'payment_reference': d['REFERENCE'] if move_type in ['out_invoice', 'out_refund'] else d['COMMUNICATION'],
            'efficy_reference': d['REFERENCE'],
            'partner_id': partner_id.id,
            'invoice_date': d['D_INVOICE'],
            'move_type': move_type,
            'journal_id': self.with_context(default_move_type=move_type).with_company(company_id.id)._get_default_journal().id,
            'invoice_date_due': d.get('EXP_DATE') or d.get('D_INVOICE'),
            'currency_id': currency_id.id,
            'invoice_line_ids': line_vals,
            'efficy_mapping_model_id': self.env.ref('efficy_accounting.efficy_mapping_model_customer_invoices').id,
        }

    def _postprocess_data(self, d, log):

        self.ensure_one()

        sign = 1
        if self.amount_total < 0 and self.move_type in ['out_invoice', 'in_invoice']:
            sign = -1
            self.action_switch_invoice_into_refund_credit_note()

        if abs(self.amount_total - d['TOTAL_WITH_VAT'] * sign) <= 0.011:
            log.info("Total %s matches the total_with_vat from Efficy : %s" % (
                self.amount_total, d['TOTAL_WITH_VAT']))
        else:
            log.error("Total %s does not match the total_with_vat from Efficy : %s" % (
                self.amount_total, d['TOTAL_WITH_VAT']))

    def _create_empty(self, d):

        if self:
            return

        self.create({
            'efficy_reference': d.get('REFERENCE', 'False'),
            'efficy_entity': 'Rela',
            'efficy_key': d.get('K_RELATION'),
        })

    def run_query(self, date_from=False, noupdate=False, limit=False, company=True, document=True, relation=True, file=True):

        def ans_format(ans):
            dic_document = []
            dic_company = []
            dic_relation = []
            dic_file = []
            keys_document = []
            keys_company = []
            keys_relation = []
            keys_file = []

            fields_document = ['K_DOCUMENT', 'R_F_INVOICE_STATUS', 'REFERENCE', 'COMMUNICATION', 'D_INVOICE', 'EXP_DATE', 'R_CURRCY', 'TOTAL_WITH_VAT', 'TOTAL_NO_VAT', 'K_COMPANY']
            fields_company = ['K_COMPANY', 'NAME_1', 'F_IBAN', 'STREET', 'COUNTRYSHORT', 'POSTCODE', 'CITY', 'EMAIL1', 'VAT']
            fields_relation = ['K_RELATION', 'COMMENT', 'QUANTITY', 'DISCOUNT', 'PRICE', 'F_MULTIPLIER', 'F_D_S_RECO', 'F_D_E_RECO', 'F_ACCOUNTING_TYPE', 'VAT_1', 'K_DOCUMENT']
            fields_file = ['K_FILE', 'VERSION', 'K_DOCUMENT']

            for func in ans[0]['@func']:
                for d in func['#result']['#data']:
                    if len(d.get('REFERENCE').split('-')) > 1 and int(d.get('REFERENCE').split('-')[1]) < 2021:
                        continue
                    if len(d.get('REFERENCE').split('-')) > 2 and d.get('REFERENCE').split('-')[2] not in self.env['res.company'].search([]).mapped('efficy_code'):
                        continue
                    if d.get('K_DOCUMENT') not in keys_document:
                        dic_document.append({f: d.get(f) for f in fields_document})
                        keys_document.append(d.get('K_DOCUMENT'))
                    if d.get('K_COMPANY') not in keys_company:
                        dic_company.append({f: d.get(f) for f in fields_company})
                        keys_company.append(d.get('K_COMPANY'))
                    if d.get('K_RELATION') not in keys_relation:
                        dic_relation.append({f: d.get(f) for f in fields_relation})
                        keys_relation.append((d.get('K_RELATION')))
                    if d.get('K_FILE') not in keys_file:
                        dic_file.append({f: d.get(f) for f in fields_file})
                        keys_file.append((d.get('K_FILE')))

            return dic_document, dic_company, dic_relation, dic_file

        if self:
            payload = [{
                '@name': 'api',
                '@func': [{'@name': 'query', 'key': 12004, 'param1': rec.efficy_key} for rec in self if rec.efficy_key]
            }]
        elif date_from:
            payload = [{
                '@name': 'api',
                '@func': [{'@name': 'query', 'key': 11969, 'param1': date_from.strftime("%d/%m/%Y")}]
            }]
        else:
            payload = [{
                '@name': 'api',
                '@func': [{'@name': 'query', 'key': 11969}]
            }]

        ans = self.env['efficy.mapping.model'].json_request(payload)
        # datas = ans_format(ans)
        dic_document, dic_company, dic_relation, dic_file = ans_format(ans)

        sync_date = fields.Datetime.now()
        sync_sequence = self.env.ref('efficy_accounting.seq_efficy_sync_log').next_by_id()
        self = self.with_context(sync_date=sync_date, sync_sequence=sync_sequence)

        if company:
            self.env['res.partner'].process_data(dic_company, 'K_COMPANY', 'Comp')
        if document:
            self.with_context(line_data=dic_relation).env['account.move'].process_data(dic_document, 'K_DOCUMENT', 'Docu')

        if file:
            self.env['efficy.invoice.attachment'].process_data(dic_file, 'K_FILE', 'File')
        # if relation:
        #     self.env['account.move.line'].process_data(dic_relation, 'K_RELATION', 'Rela')

        if not self:
            self.env.company.efficy_last_sync_date = sync_date

    def button_get_moves_with_lines(self):
        self.get_moves_with_lines()

    @api.model
    def get_moves_with_lines(self, date_from=False, date_to=False, noupdate=False, limit=False):

        class SkippedException(Exception):
            pass

        def ans_format(ans):
            dic = {}
            keys = []

            fields_document = ['K_DOCUMENT', 'R_F_INVOICE_STATUS', 'REFERENCE', 'COMMUNICATION', 'D_INVOICE', 'EXP_DATE', 'R_CURRCY', 'TOTAL_WITH_VAT', 'TOTAL_NO_VAT']
            fields_company = ['K_COMPANY', 'NAME_1', 'F_IBAN', 'STREET', 'COUNTRYSHORT', 'POSTCODE', 'CITY', 'EMAIL1', 'VAT']
            fields_relation = ['K_RELATION', 'COMMENT', 'QUANTITY', 'DISCOUNT', 'PRICE', 'F_MULTIPLIER', 'F_D_S_RECO', 'F_D_E_RECO', 'F_ACCOUNTING_TYPE', 'VAT_1']
            fields_file = ['K_FILE', 'VERSION']

            for func in ans[0]['@func']:
                for d in func['#result']['#data']:
                    key = d['K_DOCUMENT']
                    dic.setdefault(key, {
                        'document': {f: d.get(f) for f in fields_document},
                        'company': {f: d.get(f) for f in fields_company},
                        'relations': {},
                        'files': {},
                        'raw': [],
                    })
                    # dic[key]['relations'].append({f: d.get(f) for f in fields_relation})
                    dic[key]['relations'][d['K_RELATION']] = {f: d.get(f) for f in fields_relation}
                    # dic[key]['files'].append({f: d.get(f) for f in fields_file})
                    dic[key]['files'][d['K_FILE']] = {f: d.get(f) for f in fields_file}
                    dic[key]['raw'].append(d)
                    keys.append(key)

            return dic

        class Log():

            def reset(self, date, sequence, entity, key, data, raw):
                self.messages = []
                self.status = False
                self.date = date
                self.sequence = sequence
                self.entity = entity
                self.key = key
                self.data = data
                self.raw = raw

            def skipped(self, message):
                self.messages.append('<li><b style="color:gray">SKIPPED</b> %s </li>' % message)
                self.status = 'skipped'
                if record:
                    record.efficy_sync_status = 'skipped'
                raise SkippedException()

            def info(self, message):
                self.messages.append('<li><b style="color:green">INFO</b> %s </li>' % message)

            def warning(self, message):
                self.messages.append('<li><b style="color:orange">WARNING</b> %s </li>' % message)
                self.status = 'warning'

            def error(self, message):
                self.messages.append('<li><b style="color:red">ERROR</b> %s </li>' % message)
                self.status = 'error'
                if record:
                    record.efficy_sync_status = 'error'

            def failed(self, message):
                self.messages.append('<li><b style="color:red">FAILED</b> %s </li>' % message)
                self.status = 'failed'
                record.efficy_sync_status = 'failed'
                # _logger.(message)

            def done(self):
                self.status = self.status or 'success'
                record.efficy_sync_status = self.status

            def get_message(self):
                return "<ul>%s</ul>" % ''.join(self.messages)

            def get_create_vals(self):
                return {
                    'sync_message': self.get_message(),
                    'sync_date': self.date,
                    'sync_sequence': self.sequence,
                    'efficy_entity': self.entity,
                    'efficy_key': self.key,
                    'sync_data': self.data,
                    'sync_status': self.status,
                    'sync_raw_data': self.raw,
                }

        def parse_reference(ref):

            # CHECK REFERENCE + SPLIT
            try:
                type, year, country = ref.split('-')[:3]
            except:
                log.skipped("Bad formatted reference: %s" % ref)

            # CHECK YEAR
            if int(year) < 2021:
                log.skipped("Skipped record from date %s : %s" % (year, ref))

            # CHECK COMPANY
            company_id = companies.get(country, False)
            if not company_id:
                log.skipped("No company found with code %s for %s" % (country, ref))

            # SET MOVE TYPE
            move_type = 'entry'
            if type == 'INV':
                move_type = 'out_invoice'
            if type == 'IINV':
                move_type = 'in_invoice'
            if type == 'EXP':
                move_type = 'in_invoice'

            return move_type, company_id

        def process_company(d):

            # SEARCH BANK
            bank_id = self.env['res.partner.bank'].search([('acc_number', '=', d['F_IBAN'])])

            # CHECK VAT
            vat = False
            if d.get('VAT'):
                vat_number = d['VAT'].replace(' ', '')
                if self.env['res.partner'].simple_vat_check(d['COUNTRYSHORT'], vat_number):
                    vat = "%s%s" % (d['COUNTRYSHORT'], vat_number)
                else:
                    record.efficy_sync_status = 'warning'
                    log.warning("Bad vat format: %s%s" % (d['COUNTRYSHORT'], vat_number))

            partner_id = self.env['res.partner'].search([('efficy_key', '=', d['K_COMPANY'])])

            partner_vals = {
                'efficy_key': d['K_COMPANY'],
                'efficy_entity': 'Comp',
                'name': d['NAME_1'],
                #'bank_ids': bank_id if bank_id else [(0, 0, {'acc_number': d['F_IBAN']})],
                'street': d['STREET'],
                'country_id': countries[d['COUNTRYSHORT']].id if d['COUNTRYSHORT'] else False,
                'zip': d['POSTCODE'],
                'city': d['CITY'],
                'vat': vat,
                'email': d['EMAIL1'],
                'company_type': 'company',
                'efficy_mapping_model_id': self.env.ref('efficy_accounting.efficy_mapping_model_companies').id,
            }

            # PARTNER WRITE OR CREATE
            if partner_id:
                partner_id.write(partner_vals)
            else:
                partner_id = partner_id.create(partner_vals)

            return partner_id

        def process_files(data):

            update_vals = []

            for d in data.values():
                record = self.env['efficy.invoice.attachment'].search([
                    ('efficy_key', '=', d['K_FILE']),
                    ('efficy_entity', '=', 'File')
                ])
                update_vals.append((
                    record and 1 or 0,
                    record.id or 0,
                    {
                        'efficy_key': d['K_FILE'],
                        'efficy_entity': 'File',
                        'version': d['VERSION']
                    }
                ))
            return update_vals

        def process_relations(data, journal_id, invoice_date=False):

            line_vals = [(5, 0, 0)]

            for d in data.values():

                # SEARCH ANALYTIC ACCOUNT
                domain = [
                    ('name', '=', d['F_ACCOUNTING_TYPE']),
                    ('company_id', 'in', [company_id.id, False])
                ]
                analytic_account = self.env['account.analytic.account'].search(domain)
                if len(analytic_account) > 1:
                    record.efficy_sync_status = 'warning'
                    log.warning("Multiple analytic accounts found for %s. Found %s" % (
                        domain, analytic_account.read(['name', 'company_id'])))
                    analytic_account = analytic_account[0]
                if len(analytic_account) == 0:
                    record.efficy_sync_status = 'warning'
                    log.warning("No analytic accounts found for %s" % domain)

                # SEARCH ANALYTIC DEFAULT
                domain = []
                if company_id:
                    domain.append(('company_id', 'in', [company_id.id, False]))
                if analytic_account and move_type in ['out_invoice', 'out_refund']:
                    domain.append(('analytic_id', '=', analytic_account.id))
                if partner_id and move_type in ['in_invoice', 'in_refund']:
                    domain.append(('partner_id', '=', partner_id.id))
                analytic_default = self.env['account.analytic.default'].search(domain)

                if len(analytic_default) > 1:
                    record.efficy_sync_status = 'warning'
                    log.warning("Multiple analytic default found for %s. Found %s" % (
                        domain, analytic_default.read(['analytic_id', 'partner_id', 'company_id'])))
                    analytic_default = analytic_default[0]
                if len(analytic_default) == 0:
                    record.efficy_sync_status = 'warning'
                    log.warning("No analytic default found for %s" % domain)

                if analytic_default.account_id:
                    log.info("Using account from analytic default : %s" % analytic_default.read(
                        ['id', 'analytic_id', 'company_id', 'partner_id']))
                else:
                    log.info("Using account from journal")
                account_id = analytic_default.account_id or journal_id.default_account_id

                if account_id.deprecated:
                    record.efficy_sync_status = 'failed'
                    log.error("Account deprecated: %s" % account_id.read(['name', 'code', 'company_id']))
                    raise UserError("Account deprecated: %s\n" % account_id.read(['name', 'code', 'company_id']))

                default_tax_ids = account_id.tax_ids
                fiscal_position_id = self.with_company(company_id.id).env[
                    'account.fiscal.position'].get_fiscal_position(partner_id.id)
                tax_ids = fiscal_position_id.map_tax(default_tax_ids)
                tax_account_ids = tax_ids.invoice_repartition_line_ids.account_id

                if any(tax_account_ids.mapped('deprecated')):
                    record.efficy_sync_status = 'failed'
                    log.failed("Account deprecated on tax repartition: %s" % tax_account_ids.read(
                        ['name', 'code', 'company_id']))
                    raise UserError("Account deprecated on tax repartition: %s\n" % tax_account_ids.read(
                        ['name', 'code', 'company_id']))

                if any((partner_id.propery_account_receivable_id + partner_id.property_account_payable_id).mapped('deprecated')):
                    log.failed("Account deprecated on partner's property account: %s" % tax_account_ids.read(
                        ['name', 'code', 'company_id']))
                    raise UserError("Account deprecated on partner's property account: %s\n" % tax_account_ids.read(
                        ['name', 'code', 'company_id']))

                log.info("- Default taxes : %s, fiscal position : %s, Using taxes : %s\n" % (
                    default_tax_ids.read(['id', 'name', 'type_tax_use', 'company_id']),
                    fiscal_position_id.read(['id', 'name', 'company_id']),
                    tax_ids.read(['id', 'name', 'type_tax_use', 'company_id'])
                ))

                line_vals.append((0, 0, {
                    'name': d['COMMENT'],
                    'analytic_account_id': analytic_account.id,
                    'account_id': account_id.id,
                    'analytic_tag_ids': analytic_default.analytic_tag_ids.ids,
                    'end_recognition_date': d['F_D_E_RECO'] if d['F_D_E_RECO'] not in ['30/12/1899', '1899-12-30'] else invoice_date,
                    'start_recognition_date': d['F_D_S_RECO'] if d['F_D_S_RECO'] not in ['30/12/1899', '1899-12-30'] else invoice_date,
                    'quantity': d['QUANTITY'],
                    'discount': d.get('DISCOUNT', 0),
                    'price_unit': round(d['PRICE'] * d.get('F_MULTIPLIER', 100) / 100, 2),
                    'tax_ids': tax_ids,
                    # 'efficy_entity': 'Rela',
                    'efficy_key': d['K_RELATION']
                }))

            return line_vals

        if self:
            payload = [{
                '@name': 'api',
                '@func': [{'@name': 'query', 'key': 12004, 'param1': rec.efficy_key} for rec in self if rec.efficy_key]
            }]
        elif date_from and date_to:
            payload = [{
                '@name': 'api',
                '@func': [{'@name': 'query', 'key': 11969, 'param1': date_from.strftime("%d/%m/%Y"), 'param2': date_to.strftime("%d/%m/%Y")}]
            }]
        elif date_from:
            payload = [{
                '@name': 'api',
                '@func': [{'@name': 'query', 'key': 11969, 'param1': date_from.strftime("%d/%m/%Y")}]
            }]
        elif date_to:
            payload = [{
                '@name': 'api',
                '@func': [{'@name': 'query', 'key': 11969, 'param2': date_to.strftime("%d/%m/%Y")}]
            }]
        else:
            payload = [{
                '@name': 'api',
                '@func': [{'@name': 'query', 'key': 11969}]
            }]

        ans = self.env['efficy.mapping.model'].json_request(payload)
        data = ans_format(ans)

        sync_date = fields.Datetime.now()
        sync_sequence = self.env.ref('efficy_accounting.seq_efficy_sync_log').next_by_id()
        processed_records = self.env['account.move']
        skipped_records = self.env['account.move']
        failed_records = self.env['account.move']
        log = Log()
        log_vals_batch = []

        companies = {company_id.efficy_code: company_id for company_id in self.env['res.company'].search([])}
        currencies = {currency_id.name: currency_id for currency_id in self.env['res.currency'].search([])}
        countries = {country_id.code: country_id for country_id in self.env['res.country'].search([])}

        i = 0
        start_loop = time()
        start = start_loop

        for key in data:

            if i % 100 == 0:
                _logger.info("processed %s records out of %s. Took %s sec" % (i, len(data), time() - start))
                start = time()
            i += 1

            if limit and i >= limit:
                _logger.warning("Processing limit reached, stopping")
                break

            _logger.info("Processing key %s" % key)

            d = data[key]
            raw = json.dumps(d.pop('raw'))
            log.reset(date=sync_date, sequence=sync_sequence, entity='Docu', key=key, data=json.dumps(d, indent=2), raw=raw)

            record = self.search([('efficy_entity', '=', 'Docu'), ('efficy_key', '=', key)])

            try:

                if record and noupdate:
                    log.skipped("Existing, no update")

                if record and record.state not in ['draft']:
                    log.skipped("Entry posted, skipping")

                move_type, company_id = parse_reference(d['document']['REFERENCE'])
                journal_id = self.with_context(default_move_type=move_type).with_company(company_id.id)._get_default_journal()
                partner_id = process_company(d['company'])
                attachment_vals = process_files(d['files'])

                line_vals = process_relations(d['relations'], journal_id, d['document'].get('D_INVOICE'))

                # SEARCH CURRENCY
                currency_id = currencies.get(d['document']['R_CURRCY'], False)
                if not currency_id:
                    log.failed("No currency found for %s" % d['document']['R_CURRCY'] or 'None')

                move_vals = {
                    'efficy_key': d['document']['K_DOCUMENT'],
                    'efficy_entity': 'Docu',
                    'approbation_status': d['document']['R_F_INVOICE_STATUS'],
                    'payment_reference': d['document']['REFERENCE'] if move_type in ['out_invoice', 'out_refund'] else d['document']['COMMUNICATION'],
                    'efficy_reference': d['document']['REFERENCE'],
                    'partner_id': partner_id.id,
                    'invoice_date': d['document']['D_INVOICE'],
                    'move_type': move_type,
                    'journal_id': journal_id.id,
                    'invoice_date_due': d['document'].get('EXP_DATE') or d['document'].get('D_INVOICE'),
                    'currency_id': currency_id,
                    'efficy_mapping_model_id': self.env.ref('efficy_accounting.efficy_mapping_model_customer_invoices').id,
                    'invoice_line_ids': line_vals,
                    'efficy_attachment_ids': attachment_vals,
                }

                if record:
                    record.write(move_vals)
                else:
                    record = record.create(move_vals)

                sign = 1
                if record.amount_total < 0 and record.move_type in ['out_invoice', 'in_invoice']:
                    sign = -1
                    record.action_switch_invoice_into_refund_credit_note()

                if abs(record.amount_total - d['document']['TOTAL_WITH_VAT'] * sign) <= 0.011:
                    log.info("Total %s matches the total_with_vat from Efficy : %s" % (record.amount_total, d['document']['TOTAL_WITH_VAT']))
                else:
                    log.error("Total %s does not match the total_with_vat from Efficy : %s" % (record.amount_total, d['document']['TOTAL_WITH_VAT']))

                processed_records |= record
                log.done()

            except SkippedException as e:
                skipped_records |= record

            except Exception as e:

                record = record | self.env['account.move'].search([('efficy_entity', '=', 'Docu'), ('efficy_key', '=', key)])
                if not record:
                    record = record.create({
                        'efficy_entity': 'Docu',
                        'efficy_key': key,
                        'efficy_reference': d.get('document', {}).get('REFERENCE', False),
                        'efficy_sync_status': 'failed',
                    })

                failed_records |= record
                log.failed(e)

            finally:
                log_vals_batch.append(log.get_create_vals())

        _logger.info("Processed all records. Took %s sec" % (time() - start_loop))
        _logger.info("Processed %s records" % len(processed_records))
        _logger.info("Skipped %s records" % len(skipped_records))
        _logger.info("Failed %s records" % len(failed_records))

        _logger.info("Creating log files")
        self.env['efficy.sync.log'].create(log_vals_batch)

        if not self:
            self.env.company.efficy_last_sync_date = sync_date
        _logger.info("All done")
        return processed_records, skipped_records, failed_records


class AccountMoveLine(models.Model):
    _name = 'account.move.line'
    _inherit = ['account.move.line', 'efficy.integration.mixin']

    start_recognition_date = fields.Date()
    end_recognition_date = fields.Date()

    def _create_empty(self, d):

        if self:
            return

        move_id = self.env['account.move'].search([('efficy_entity', '=', 'Docu'), ('efficy_key', '=', d['K_DOCUMENT'])])
        if not move_id:
            return

        account_id = move_id.journal_id.default_account_id

        self.create({
            'name': d.get('COMMENT', 'False'),
            'move_id': move_id.id,
            'account_id': account_id.id
        })

    def _process_data(self, d, log):

        move_id = self.env['account.move'].search([('efficy_entity', '=', 'Docu'), ('efficy_key', '=', d['K_DOCUMENT'])])

        if not move_id:
            log.failed("The Invoice is missing; can't create invoice line")

        company_id = move_id.company_id
        move_type = move_id.move_type
        partner_id = move_id.partner_id
        journal_id = move_id.journal_id
        invoice_date = move_id.invoice_date

        # SEARCH ANALYTIC ACCOUNT
        domain = [
            ('name', '=', d['F_ACCOUNTING_TYPE']),
            ('company_id', 'in', [company_id.id, False])
        ]
        analytic_account = self.env['account.analytic.account'].search(domain)
        if len(analytic_account) > 1:
            log.warning("Multiple analytic accounts found for %s. Found %s" % (
                domain, analytic_account.read(['name', 'company_id'])))
            analytic_account = analytic_account[0]
        if len(analytic_account) == 0:
            log.warning("No analytic accounts found for %s" % domain)

        # SEARCH ANALYTIC DEFAULT
        domain = []
        if company_id:
            domain.append(('company_id', 'in', [company_id.id, False]))
        if analytic_account and move_type in ['out_invoice', 'out_refund']:
            domain.append(('analytic_id', '=', analytic_account.id))
        if partner_id and move_type in ['in_invoice', 'in_refund']:
            domain.append(('partner_id', '=', partner_id.id))
        analytic_default = self.env['account.analytic.default'].search(domain)

        if len(analytic_default) > 1:
            log.warning("Multiple analytic default found for %s. Found %s" % (
                domain, analytic_default.read(['analytic_id', 'partner_id', 'company_id'])))
            analytic_default = analytic_default[0]
        if len(analytic_default) == 0:
            log.warning("No analytic default found for %s" % domain)

        if analytic_default.account_id:
            log.info("Using account from analytic default : %s" % analytic_default.read(
                ['id', 'analytic_id', 'company_id', 'partner_id']))
        else:
            log.info("Using account from journal")
        account_id = analytic_default.account_id or journal_id.default_account_id

        if account_id.deprecated:
            log.error("Account deprecated: %s" % account_id.read(['name', 'code', 'company_id']))
            raise UserError("Account deprecated: %s\n" % account_id.read(['name', 'code', 'company_id']))

        default_tax_ids = account_id.tax_ids
        fiscal_position_id = self.with_company(company_id.id).env[
            'account.fiscal.position'].get_fiscal_position(partner_id.id)
        tax_ids = fiscal_position_id.map_tax(default_tax_ids)
        tax_account_ids = tax_ids.invoice_repartition_line_ids.account_id

        if any(tax_account_ids.mapped('deprecated')):
            log.failed("Account deprecated on tax repartition: %s" % tax_account_ids.read(
                ['name', 'code', 'company_id']))

        if any((move_id.partner_id.propery_account_receivable_id + move_id.partner_id.property_account_payable_id).mapped('deprecated')):
            log.failed("Account deprecated on partner's property account: %s" % tax_account_ids.read(
                ['name', 'code', 'company_id']))

        log.info("- Default taxes : %s, fiscal position : %s, Using taxes : %s\n" % (
            default_tax_ids.read(['id', 'name', 'type_tax_use', 'company_id']),
            fiscal_position_id.read(['id', 'name', 'company_id']),
            tax_ids.read(['id', 'name', 'type_tax_use', 'company_id'])
        ))

        return {
            'name': d['COMMENT'],
            'analytic_account_id': analytic_account.id,
            'account_id': account_id.id,
            'analytic_tag_ids': analytic_default.analytic_tag_ids.ids,
            'end_recognition_date': d['F_D_E_RECO'] if d['F_D_E_RECO'] not in ['30/12/1899',
                                                                               '1899-12-30'] else invoice_date,
            'start_recognition_date': d['F_D_S_RECO'] if d['F_D_S_RECO'] not in ['30/12/1899',
                                                                                 '1899-12-30'] else invoice_date,
            'quantity': d['QUANTITY'],
            'discount': d.get('DISCOUNT', 0),
            'price_unit': round(d['PRICE'] * d.get('F_MULTIPLIER', 100) / 100, 2),
            'tax_ids': tax_ids,
            # 'move_id': move_id.id,
        }
