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
            "select count(id) from %s where efficy_entity is not null group by efficy_entity, efficy_key having count(*) > 1;" % (self._name.replace('.', '_'))
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
    sync_status = fields.Selection([('processing', "Processing"), ('skipped', "Skipped"), ('failed', "Failed"), ('warning', "Warning"), ('success', "Success")])
    sync_message = fields.Html(default='')
    sync_data = fields.Text()
    res_model = fields.Char()
    res_id = fields.Integer()
    efficy_entity = fields.Char()
    efficy_key = fields.Char()

    def skipped(self, in_vals, message):
        vals = in_vals
        vals['sync_status'] = 'skipped'
        vals['sync_message'] = in_vals['sync_message'] + message + "\n"
        return vals
        # _logger.info(message)

    def error(self, in_vals, message):
        vals = in_vals
        vals['sync_status'] = 'failed'
        vals['sync_message'] = in_vals['sync_message'] + message + "\n"
        yield vals
        raise UserError(message)

    def warning(self, in_vals, message):
        vals = in_vals
        vals['sync_status'] = 'warning'
        vals['sync_message'] = in_vals['sync_message'] + message + "\n"
        return vals
        # _logger.warning(message)

    def info(self, in_vals, message):
        vals = in_vals
        vals['sync_message'] = in_vals['sync_message'] + message + "\n"
        return vals

    def success(self, in_vals):
        vals = in_vals
        vals['sync_status'] = 'success' if vals['sync_status'] == 'processing' else vals['sync_status']
        return vals

    def failed(self, in_vals, message):
        vals = in_vals
        vals['sync_status'] = 'failed'
        vals['sync_message'] = in_vals['sync_message'] + message + "\n"
        _logger.warning(message)
        return vals

    # def skipped(self, message):
    #     for rec in self:
    #         rec.sync_status = 'skipped'
    #         rec.sync_message += message + "\n"
    #         # _logger.info(message)
    #
    # def error(self, message):
    #     for rec in self:
    #         rec.sync_status = 'failed'
    #         rec.sync_message += message + "\n"
    #         raise UserError(message)
    #
    # def warning(self, message):
    #     for rec in self:
    #         rec.sync_status = 'warning'
    #         rec.sync_message += message + "\n"
    #         # _logger.warning(message)
    #
    # def info(self, message):
    #     for rec in self:
    #         rec.sync_message += message + "\n"
    #
    # def success(self):
    #     for rec in self:
    #         rec.sync_status = 'success' if rec.sync_status == 'processing' else rec.sync_status
    #
    # def failed(self, message):
    #     for rec in self:
    #         rec.sync_status = 'failed'
    #         rec.sync_message += message + "\n"
    #         _logger.warning(message)
