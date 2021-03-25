from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    efficy_code = fields.Char()