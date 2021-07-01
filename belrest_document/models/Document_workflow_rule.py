# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, Warning

class BelrestDocumentWorkflowRule(models.Model):
    _inherit = 'documents.workflow.rule'

    def create_record(self, documents=None):
        rv = super(BelrestDocumentWorkflowRule, self).create_record(documents=documents)
        ids = rv.get("domain")[0][2]
        for document in documents:
            messages = self.env["mail.message"].search(
                   [('model', '=', 'documents.document'), ('res_id', '=', document.id)])
            messages.write({'model': document.res_model, 'res_id': document.res_id})
        return rv

