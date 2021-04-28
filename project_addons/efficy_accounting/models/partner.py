from odoo import models, fields, api


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'efficy.integration.mixin']

    @api.model
    def sync_entity(self):
        pass

    def sync_entity_one(self):

        payload = [{
            "@name": "consult",
            "entity": "Comp",
            "key": self.efficy_key,
            "@func": [{"@name": "master"}]
        }]

        data = self.env['efficy.mapping.model'].json_request(payload)
        sync_date = fields.Datetime.now()
        sync_sequence = self.env.ref('efficy_accounting.seq_efficy_sync_log').next_by_id()
        self = self.with_context(sync_date=sync_date, sync_sequence=sync_sequence)
        dic_company = data[0]['@func'][0]['#result']['#data']
        self.process_data(dic_company, 'K_COMPANY', 'Comp')

    def button_run_query(self):
        self.run_query()

    def run_query(self, noupdate=False, limit=False):

        def ans_format(ans):
            dic_company = []
            keys_company = []

            fields_company = ['K_COMPANY', 'NAME', 'F_IBAN', 'STREET', 'COUNTRYSHORT', 'POSTCODE', 'CITY', 'EMAIL1', 'VAT']

            for func in ans[0]['@func']:
                for d in func['#result']['#data']:
                    if d.get('K_COMPANY') not in keys_company:
                        dic_company.append({f: d.get(f) for f in fields_company})
                        keys_company.append(d.get('K_COMPANY'))

            return dic_company

        self = self.filtered(lambda x: x.efficy_entity == 'Comp' and x.efficy_key)

        payload = [{
            '@name': 'api',
            '@func': [{'@name': 'query', 'key': 12241, 'param1': rec.efficy_key} for rec in self]
        }]

        ans = self.env['efficy.mapping.model'].json_request(payload)
        dic_company = ans_format(ans)

        sync_date = fields.Datetime.now()
        sync_sequence = self.env.ref('efficy_accounting.seq_efficy_sync_log').next_by_id()
        self = self.with_context(sync_date=sync_date, sync_sequence=sync_sequence)

        self.env['res.partner'].process_data(dic_company, 'K_COMPANY', 'Comp')

    @api.model
    def _process_data(self, d, log):
        # bank_id = self.env['res.partner.bank'].search([('acc_number', '=', d['F_IBAN'])])
        country_id = self.env['res.country'].search([('code', '=', d['COUNTRYSHORT'])], limit=1)

        # CHECK VAT
        vat = False
        if d.get('VAT'):
            vat_number = d['VAT'].replace(' ', '')
            if self.env['res.partner'].simple_vat_check(d['COUNTRYSHORT'], vat_number):
                vat = "%s%s" % (d['COUNTRYSHORT'], vat_number)
            else:
                log.warning("Bad vat format: %s%s" % (d['COUNTRYSHORT'], vat_number))
        else:
            log.warning("Missing TVA")

        record_vals = {
            'efficy_key': d['K_COMPANY'],
            'efficy_entity': 'Comp',
            'name': d.get('NAME') or d.get('NAME_1'),
            # 'bank_ids': bank_id and [] or [(0, 0, {'acc_number': d['F_IBAN']})],
            'street': d['STREET'],
            'country_id': country_id.id,
            'zip': d['POSTCODE'],
            'city': d['CITY'],
            'vat': vat,
            'email': d['EMAIL1'],
            'company_type': 'company',
            'efficy_mapping_model_id': self.env.ref('efficy_accounting.efficy_mapping_model_companies').id,
        }

        return record_vals

    def _create_empty(self, d):

        if self:
            return

        self.create({
            'efficy_entity': 'Comp',
            'efficy_key': d.get('K_COMPANY'),
        })

