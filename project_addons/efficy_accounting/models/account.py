from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from time import time
import logging
import requests
import json

_logger = logging.getLogger(__name__)


class EfficyInvoiceAttachment(models.Model):
    _name = 'efficy.invoice.attachment'
    _inherit = ['efficy.integration.mixin']
    _description = "Efficy Attachment"

    endpoint = fields.Char(related='move_id.company_id.efficy_database_endpoint')
    headers = fields.Char(related='move_id.company_id.efficy_database_headers')
    data_filename = fields.Char()
    version = fields.Integer()
    data = fields.Binary()
    move_id = fields.Many2one(comodel_name='account.move')

    def write(self, vals):
        for rec in self:
            if rec.data and not ('efficy_key' in vals or 'version' in vals):
                continue
            if rec.data and vals.get('efficy_key') == rec.efficy_key and vals.get('version') == rec.version:
                continue
            if not rec.move_id:
                continue
            key = rec.efficy_key or vals.get('efficy_key')
            version = rec.version or vals.get('version')
            payload = [
                {
                    '@name': 'edit',
                    'entity': rec.move_id.efficy_entity,
                    'key': rec.move_id.efficy_key,
                    'closecontext': True,
                    '@func': [
                        {
                            '@name': 'attachment',
                            'key': "%s_%s" % (key, version or 0),
                        }
                    ]
                }
            ]
            _logger.info("requested attachment %s_%s for %s-%s" % (key, version, rec.move_id.efficy_entity, rec.move_id.efficy_key))
            _logger.debug("request payload : %s" % payload)
            endpoint = self.env['res.company'].browse(1).efficy_database_endpoint
            headers = self.env['res.company'].browse(1).efficy_database_headers
            ans = requests.get(url=endpoint, json=payload, headers=json.loads(headers)).json()
            vals['data'] = ans[0]['@func'][0]['#result']
        return super(EfficyInvoiceAttachment, self).write(vals)

    def create(self, vals):
        records = super(EfficyInvoiceAttachment, self).create(vals)
        records.write({})
        return records


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'efficy.integration.mixin']

    approbation_status = fields.Selection([('Approved', 'Approved'), ('Contested', 'Contested'), ('On Hold', 'On Hold')])
    efficy_attachment_ids = fields.One2many(comodel_name='efficy.invoice.attachment', inverse_name='move_id')
    amount_residual = fields.Monetary(store=True)
    efficy_reference = fields.Char()
    efficy_sync_log_ids = fields.One2many(comodel_name='efficy.sync.log', compute="_compute_efficy_sync_log_ids")
    efficy_sync_status = fields.Selection([('processing', "Processing"), ('skipped', "Skipped"), ('failed', "Failed"), ('warning', "Warning"), ('success', "Success")])

    def _compute_efficy_sync_log_ids(self):
        for rec in self:
            rec.efficy_sync_log_ids = self.env['efficy.sync.log'].search([
                ('efficy_entity', '=', rec.efficy_entity),
                ('efficy_key', '=', rec.efficy_key)
            ])

    def name_get(self):
        return [(rec.id, rec.payment_reference) for rec in self]

    def action_switch_invoice_into_refund_credit_note(self, inverse=True):
        if inverse:
            super(AccountMove, self).action_switch_invoice_into_refund_credit_note()
        else:
            if any(move.move_type not in ('in_invoice', 'out_invoice') for move in self):
                raise ValidationError(_("This action isn't available for this document."))

            for move in self:
                reversed_move = move._reverse_move_vals({}, False)
                new_invoice_line_ids = []
                for cmd, virtualid, line_vals in reversed_move['line_ids']:
                    if not line_vals['exclude_from_invoice_tab']:
                        new_invoice_line_ids.append((0, 0,line_vals))
                if move.amount_total < 0:
                    # Inverse all invoice_line_ids
                    for cmd, virtualid, line_vals in new_invoice_line_ids:
                        line_vals.update({
                            'quantity' : line_vals['quantity'],
                            'amount_currency' : line_vals['amount_currency'],
                            'debit' : line_vals['credit'],
                            'credit' : line_vals['debit']
                        })
                move.write({
                    'move_type': move.move_type.replace('invoice', 'refund'),
                    'invoice_line_ids' : [(5, 0, 0)],
                    'partner_bank_id': False,
                })
                move.write({'invoice_line_ids' : new_invoice_line_ids})

    @api.model
    def get_moves_with_lines(self, date_from=False, key=False, noupdate=False, limit=False):

        class Log():

            messages = []
            status = False

            def __init__(self, date, sequence, entity, key, data):
                self.date = date
                self.sequence = sequence
                self.entity = entity
                self.key = key
                self.data = data

            def skipped(self, message):
                self.messages.append('<li><b style="color:gray">SKIPPED</b> %s </li>' % message)
                self.status = 'skipped'

            def info(self, message):
                self.messages.append('<li><b style="color:green">INFO</b> %s </li>' % message)

            def warning(self, message):
                self.messages.append('<li><b style="color:orange">WARNING</b> %s </li>' % message)
                self.status = 'warning'

            def error(self, message):
                self.messages.append('<li><b style="color:red">ERROR</b> %s </li>' % message)
                self.status = 'failed'
                # raise UserError(message)

            def success(self):
                self.status = 'success'

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
                }

        sync_date = fields.Datetime.now()
        sync_sequence = self.env.ref('efficy_accounting.seq_efficy_sync_log').next_by_id()

        if date_from:
            payload = [
                {
                    '@name': 'api',
                    '@func': [
                        {'@name': 'query', 'key': 11969, 'param1': date_from.strftime("%d/%m/%Y")}
                    ]
                }
            ]
        elif key:
            payload = [
                {
                    '@name': 'api',
                    '@func': [
                        {'@name': 'query', 'key': 12004, 'param1': key}
                    ]
                }
            ]
        else:
            payload = [
                {
                    '@name': 'api',
                    '@func': [
                        {'@name': 'query', 'key': 11969}
                    ]
                }
            ]

        data = self.env['efficy.mapping.model'].json_request(payload)
        data = data[0]['@func'][0]['#result']['#data']

        processed_records = self.env['account.move']
        log_vals_batch = []

        companies = {company_id.efficy_code: company_id for company_id in self.env['res.company'].search([])}
        currencies = {currency_id.name: currency_id for currency_id in self.env['res.currency'].search([])}
        countries = {country_id.code: country_id for country_id in self.env['res.country'].search([])}

        i = 0
        start_loop = time()
        start = start_loop

        for d in data:

            if i % 100 == 0:
                _logger.info("processed %s records out of %s. Took %s sec" % (i, len(data), time() - start))
                start = time()
            i += 1

            if limit and i >= limit:
                _logger.warning("Processing limit reached, stopping")
                break

            log = Log(date=sync_date, sequence=sync_sequence, entity='Docu', key=d.get('K_DOCUMENT'), data=json.dumps(d, indent=2))

            record = self.search([('efficy_entity', '=', 'Docu'), ('efficy_key', '=', d['K_DOCUMENT'])])

            if record and noupdate:
                record.efficy_sync_status = 'skipped'
                log.skipped("Existing, no update")
                continue

            if record and record.state not in ['draft']:
                record.efficy_sync_status = 'skipped'
                log.skipped("Entry posted, skipping")
                continue

            if record and record not in processed_records:
                record.line_ids = [(5, 0, 0)]

            try:

                # CHECK REFERENCE + SPLIT
                try:
                    type, year, country = d['REFERENCE'].split('-')[:3]
                except:
                    record.efficy_sync_status = 'skipped'
                    log.skipped("Bad formatted reference: %s" % d['REFERENCE'])
                    continue

                # CHECK YEAR
                if int(year) < 2021:
                    record.efficy_sync_status = 'skipped'
                    log.skipped("Skipped record from date %s : %s" % (year, d['REFERENCE']))
                    continue

                # CHECK COMPANY
                company_id = companies.get(country, False)
                if not company_id:
                    log.skipped("No company found with code %s for %s" % (country, d['REFERENCE']))
                    continue

                # SET MOVE TYPE
                move_type = 'entry'
                if type == 'INV':
                    move_type = 'out_invoice'
                if type == 'IINV':
                    move_type = 'in_invoice'
                if type == 'EXP':
                    move_type = 'in_invoice'

                # SEARCH DEFAULT JOURNAL
                journal_id = self.with_context(default_move_type=move_type).with_company(company_id.id)._get_default_journal()

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

                # FIND PARTNER
                partner_id = self.env['res.partner'].search([('efficy_key', '=', d['K_COMPANY'])])

                partner_vals = {
                    'efficy_key': d['K_COMPANY'],
                    'efficy_entity': 'Comp',
                    'name': d['NAME_1'],
                    'bank_ids': bank_id if bank_id else [(0, 0, {'acc_number': d['F_IBAN']})],
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

                # SEARCH CURRENCY
                currency_id = currencies[d['R_CURRCY']] if d['R_CURRCY'] else False
                if not currency_id:
                    record.efficy_sync_status = 'failed'
                    log.error("No currency found for %s" % d['R_CURRCY'] or 'None')
                    raise UserError("No currency found for %s\n" % d['R_CURRCY'] or 'None')

                # SEARCH ANALYTIC ACCOUNT
                domain = [
                    ('name', '=', d['F_ACCOUNTING_TYPE']),
                    ('company_id', 'in', [company_id.id, False])
                ]
                analytic_account = self.env['account.analytic.account'].search(domain)
                if len(analytic_account) > 1:
                    record.efficy_sync_status = 'warning'
                    log.warning("Multiple analytic accounts found for %s. Found %s" % (domain, analytic_account.read(['name', 'company_id'])))
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
                    log.warning("Multiple analytic default found for %s. Found %s" % (domain, analytic_default.read(['analytic_id', 'partner_id', 'company_id'])))
                    analytic_default = analytic_default[0]
                if len(analytic_default) == 0:
                    record.efficy_sync_status = 'warning'
                    log.warning("No analytic default found for %s" % domain)

                if analytic_default.account_id:
                    log.info("Using account from analytic default : %s" % analytic_default.read(['id', 'analytic_id', 'company_id', 'partner_id']))
                else:
                    log.info("Using account from journal")
                account_id = analytic_default.account_id or journal_id.default_account_id

                if account_id.deprecated:
                    record.efficy_sync_status = 'failed'
                    log.error("Account deprecated: %s" % account_id.read(['name', 'code', 'company_id']))
                    raise UserError("Account deprecated: %s\n" % account_id.read(['name', 'code', 'company_id']))

                default_tax_ids = account_id.tax_ids
                fiscal_position_id = self.with_company(company_id.id).env['account.fiscal.position'].get_fiscal_position(partner_id.id)
                tax_ids = fiscal_position_id.map_tax(default_tax_ids)
                tax_account_ids = tax_ids.invoice_repartition_line_ids.account_id
                
                if any(tax_account_ids.mapped('deprecated')):
                    record.efficy_sync_status = 'failed'
                    log.error("Account deprecated on tax repartition: %s" % tax_account_ids.read(['name', 'code', 'company_id']))
                    raise UserError("Account deprecated on tax repartition: %s\n" % tax_account_ids.read(['name', 'code', 'company_id']))

                log.info("- Default taxes : %s, fiscal position : %s, Using taxes : %s\n" % (
                    default_tax_ids.read(['id', 'name', 'type_tax_use', 'company_id']),
                    fiscal_position_id.read(['id', 'name', 'company_id']),
                    tax_ids.read(['id', 'name', 'type_tax_use', 'company_id'])
                ))

                if sum(tax_ids.mapped('amount')) != d['VAT_1']:
                    log.warning("VAT amount from %s does not match the one from Efficy: %s" % (tax_ids.read(['id', 'name', 'amount']), d['VAT_1']))

                # todo: multiplier
                line_vals = {
                    'name': d['COMMENT'],
                    'analytic_account_id': analytic_account.id,
                    'account_id': account_id.id,
                    'analytic_tag_ids': analytic_default.analytic_tag_ids.ids,
                    'end_recognition_date': d['F_D_E_RECO'] if d['F_D_E_RECO'] not in ['30/12/1899', '1899-12-30'] else d['D_INVOICE'],
                    'start_recognition_date': d['F_D_S_RECO'] if d['F_D_S_RECO'] not in ['30/12/1899', '1899-12-30'] else d['D_INVOICE'],
                    'quantity': d['QUANTITY'],
                    'discount': d['DISCOUNT'],
                    'price_unit': d['PRICE'],
                    'tax_ids': tax_ids,
                }

                move_vals = {
                    'efficy_key': d['K_DOCUMENT'],
                    'efficy_entity': 'Docu',
                    'approbation_status': d['R_F_INVOICE_STATUS'],
                    'payment_reference': d['REFERENCE'] if move_type in ['out_invoice', 'out_refund'] else d['COMMUNICATION'],
                    'efficy_reference': d['REFERENCE'],
                    'partner_id': partner_id.id,
                    'invoice_date': d['D_INVOICE'],
                    'move_type': move_type,
                    'journal_id': journal_id.id,
                    # 'invoice_date_due': d['D_DUE'],
                    'invoice_date_due': d.get('EXP_DATE') or d.get('D_INVOICE'),
                    'currency_id': currency_id,
                    'efficy_mapping_model_id': self.env.ref('efficy_accounting.efficy_mapping_model_customer_invoices').id,
                    # 'efficy_attachment_ref': "%s_%s" % (d['K_FILE'], d['VERSION']),
                    'invoice_line_ids': [(0, 0, line_vals)],
                }

                if record:
                    record.write(move_vals)
                else:
                    record = record.create(move_vals)

                if record.amount_total < 0 and record.move_type in ['out_invoice', 'in_invoice']:
                    record.action_switch_invoice_into_refund_credit_note(inverse=False)

                log.success()
                record.efficy_sync_status = log.status

            except Exception as e:
                log.error(str(e))
                _logger.warning(str(e))

                if record:
                    record.write({
                        'efficy_sync_status': 'failed',
                    })
                else:
                    record = record.create({
                        'efficy_entity': 'Docu',
                        'efficy_key': d.get('K_DOCUMENT', False),
                        'efficy_reference': d.get('REFERENCE', False),
                        'efficy_sync_status': 'failed',
                    })

            finally:
                log_vals_batch.append(log.get_create_vals())
                processed_records |= record

        _logger.info("Processed all records. Took %s sec" % (time() - start_loop))
        _logger.info("Processed %s records" % len(processed_records))
        _logger.info("Post processing operations")

        # processed_records.filtered(lambda x: x.amount_total < 0 and record.move_type in ['out_invoice', 'in_invoice']).action_switch_invoice_into_refund_credit_note(inverse=False)

        self.env.company.efficy_last_sync_date = sync_date
        self.env['efficy.sync.log'].create(log_vals_batch)
        _logger.info("All done")
        return processed_records


class AccountMoveLine(models.Model):
    _name = 'account.move.line'
    _inherit = ['account.move.line', 'efficy.integration.mixin']

    start_recognition_date = fields.Date()
    end_recognition_date = fields.Date()


