from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _name = 'account.move.line'
    _inherit = ['account.move.line', 'efficy.integration.mixin']

    start_recognition_date = fields.Date()
    end_recognition_date = fields.Date()
    price_subtotal_efficy = fields.Float()
    price_subtotal_diff = fields.Float(compute='_compute_total_diff', string="Subtotal diff", digits=(1, 4))

    @api.depends('price_subtotal_efficy', 'price_subtotal')
    def _compute_total_diff(self):
        for rec in self:
            rec.price_subtotal_diff = rec.price_subtotal_efficy - rec.price_subtotal

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

        if any(partner_id.with_company(company_id).property_account_receivable_id.mapped('deprecated')):
            log.failed("Account deprecated on partner's property account: %s" % partner_id.with_company(
                company_id).property_account_receivable_id.read(
                ['name', 'code', 'company_id']))

        if any(partner_id.with_company(company_id).property_account_payable_id.mapped('deprecated')):
            log.failed("Account deprecated on partner's property account: %s" % partner_id.with_company(
                company_id).property_account_payable_id.read(
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
            'price_unit': d['PRICE'] * d.get('F_MULTIPLIER', 100) / 100,
            'tax_ids': tax_ids,
            # 'move_id': move_id.id,
            'price_subtotal_efficy': d['TOTAL']
        }
