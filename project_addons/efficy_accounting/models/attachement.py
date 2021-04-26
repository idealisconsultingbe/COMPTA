from odoo import models, fields, api
import requests
import logging
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

    @api.model
    def get_attachment_data(self, entity, key, file_key, file_version):
        payload = [
            {
                '@name': 'edit',
                'entity': entity,
                'key': key,
                'closecontext': True,
                '@func': [
                    {
                        '@name': 'attachment',
                        'key': "%s_%s" % (file_key, file_version or 0),
                    }
                ]
            }
        ]
        _logger.info("requested attachment %s_%s for %s-%s" % (file_key, file_version, self.move_id.efficy_entity, self.move_id.efficy_key))
        _logger.debug("request payload : %s" % payload)
        endpoint = self.env.company.efficy_database_endpoint
        headers = self.env.company.efficy_database_headers
        ans = requests.get(url=endpoint, json=payload, headers=json.loads(headers)).json()

        if ans[0].get('#error'):
            raise ValueError("Can't get the attachment from Efficy : %s" % (ans[1]))
        return ans[0]['@func'][0]['#result']

    @api.model
    def _process_data(self, d, log):
        record_vals = {
            'efficy_key': d['K_FILE'],
            'efficy_entity': 'File',
            'version': d['VERSION'],
            'data': self.get_attachment_data('Docu', d['K_DOCUMENT'], d['K_FILE'], d['VERSION'])
        }

        return record_vals

