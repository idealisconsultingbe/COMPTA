# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    tesseract_path = fields.Char(string="Path to tesseract exe", config_parameter='documents_sorting.tesseract_path')
    poppler_path = fields.Char(string="Path to poppler exe", config_parameter='documents_sorting.poppler_path')


