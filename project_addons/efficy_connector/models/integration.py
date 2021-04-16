from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import json
import logging

_logger = logging.getLogger(__name__)


class EfficyIntegrationMixin(models.AbstractModel):
    _name = "efficy.integration.mixin"
    _description = "Efficy Integration Mixin"

    # active = fields.Boolean(default=True)
    efficy_mapping_model_id = fields.Many2one(comodel_name='efficy.mapping.model')
    efficy_entity = fields.Char(copy=False)
    efficy_key = fields.Char(copy=False)
    efficy_ref = fields.Char(compute='_compute_efficy_ref')

    @api.constrains('efficy_entity', 'efficy_key')
    def _verify_efficy_unique(self):
        self.sudo().env.cr.execute(
            "SELECT count(id) FROM %s WHERE efficy_entity IS NOT null GROUP BY efficy_entity, efficy_key HAVING count(*) > 1;" % (
                self._name.replace('.', '_'))
        )
        if self.sudo().env.cr.fetchall():
            raise UserError("Efficy entity-key must be unique (%s)" % self)

    def _compute_efficy_ref(self):
        for rec in self:
            rec.efficy_ref = "%s-%s" % (rec.efficy_entity or '', rec.efficy_key or '')

    def efficy_update_records(self):
        self.env['efficy.mapping.model'].update(self)

    def efficy_sync(self):
        batches = {}
        for rec in self.filtered(lambda x: x.efficy_mapping_model_id and x.efficy_key and x.efficy_entity):
            batches.setdefault(rec.efficy_mapping_model_id, []).append(rec.efficy_key)
        for b in batches:
            b.pull_records_batch(batches[b])




class EfficySyncLog(models.Model):
    _name = 'efficy.sync.log'
    _description = "Efficy Sync Log"

    sync_sequence = fields.Char()
    sync_date = fields.Datetime()
    sync_batch = fields.Char()
    sync_status = fields.Selection([('processing', "Processing"), ('skipped', "Skipped"), ('failed', "Failed"), ('warning', "Warning"), ('success', "Success"), ('error', 'Error')])
    sync_message = fields.Html(default='')
    sync_data = fields.Text()
    sync_raw_data = fields.Text()
    res_model = fields.Char()
    res_id = fields.Integer()
    efficy_entity = fields.Char()
    efficy_key = fields.Char()

