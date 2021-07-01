# Copyright 2020 Idealis Consulting
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api , _

class IcDocumentsDocument(models.Model):
    _inherit = "documents.document"

    ic_local_url = fields.Char(related="attachment_id.local_url")