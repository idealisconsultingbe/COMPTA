from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.addons.efficy_accounting.models.tools import Log
import traceback
from time import time
import json
import logging

_logger = logging.getLogger(__name__)


class EfficyIntegrationMixin(models.AbstractModel):
    _name = "efficy.integration.mixin"
    _description = "Efficy Integration Mixin"
    _sql_constraints = [('entity_key_unique', 'unique(efficy_entity, efficy_key)', "Efficy entity-key must be unique")]

    # active = fields.Boolean(default=True)
    efficy_mapping_model_id = fields.Many2one(comodel_name='efficy.mapping.model')
    efficy_entity = fields.Char(copy=False)
    efficy_key = fields.Char(copy=False)
    efficy_ref = fields.Char(compute='_compute_efficy_ref')
    efficy_sync_log_ids = fields.One2many(comodel_name='efficy.sync.log', compute="_compute_efficy_sync_log_ids")
    # todo: compute form logs
    efficy_sync_status = fields.Selection([
        ('processing', "Processing"),
        ('skipped', "Skipped"),
        ('failed', "Failed"),
        ('warning', "Warning"),
        ('success', "Success"),
        ('error', 'Error')
    ], compute='_compute_efficy_sync_status')

    @api.depends('efficy_sync_log_ids')
    def _compute_efficy_sync_status(self):
        for rec in self:
            rec.efficy_sync_status = rec.efficy_sync_log_ids[-1].sync_status if rec.efficy_sync_log_ids else False

    def _compute_efficy_sync_log_ids(self):
        for rec in self:
            rec.efficy_sync_log_ids = self.env['efficy.sync.log'].search([
                ('efficy_entity', '=', rec.efficy_entity),
                ('efficy_key', '=', rec.efficy_key)
            ])

    def _compute_efficy_ref(self):
        for rec in self:
            rec.efficy_ref = "%s-%s" % (rec.efficy_entity or '', rec.efficy_key or '')

    def _preprocess_data(self, d, log):
        pass

    @api.model
    def _process_data(self, d, log):
        pass

    def _postprocess_data(self, d, log):
        pass

    @api.model
    def process_data(self, datas, key_field, entity, noupdate=False, limit=False):
        """
        d is a list of dictionaries of efficy_field: value
        """

        class SkippedException(Exception):
            pass

        processed_records = self.env[self._name]
        log = Log()
        log_vals_batch = []

        i = 0
        start_loop = time()
        start = start_loop

        for d in datas:

            if i % 100 == 0:
                _logger.info("processed %s records out of %s. Took %s sec" % (i, len(data), time() - start))
                start = time()
            i += 1

            if limit and i >= limit:
                _logger.warning("Processing limit reached, stopping")
                break

            key = d[key_field]
            entity = entity

            _logger.info("Processing key %s" % key)

            log.reset(date=self._context.get('sync_date'), sequence=self._context.get('sync_sequence'),
                      entity=entity, key=key, data=json.dumps(d, indent=2))

            # SEARCH BANK
            record = self.env[self._name].search([
                ('efficy_entity', '=', entity),
                ('efficy_key', '=', key)
            ])

            try:

                if record and noupdate:
                    log.skipped("Existing, no update")

                record._preprocess_data(d, log)

                record_vals = self._process_data(d, log)

                # PARTNER WRITE OR CREATE
                if record:
                    record.write(record_vals)
                else:
                    record = record.create(record_vals)

                record._postprocess_data(d, log)

                processed_records |= record

                log.done()

            except SkippedException as e:
                log.skipped(e)
            except Exception as e:
                log.failed(e)
            finally:
                log_vals_batch.append(log.get_create_vals())

        self.env['efficy.sync.log'].create(log_vals_batch)

        return processed_records


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
    sync_traceback = fields.Text()

