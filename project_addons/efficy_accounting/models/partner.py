from odoo import models, fields, api


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'efficy.integration.mixin']

    @api.model
    def _process_data(self, d, log):
        bank_id = self.env['res.partner.bank'].search([('acc_number', '=', d['F_IBAN'])])
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
            'name': d['NAME_1'],
            'bank_ids': bank_id if bank_id else [(0, 0, {'acc_number': d['F_IBAN']})],
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

