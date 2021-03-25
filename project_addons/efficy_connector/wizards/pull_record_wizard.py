from odoo import models, fields


class EfficyPullWizard(models.TransientModel):
    _name = 'efficy.pull.wizard'
    _description = "Efficy Pull Wizard"

    def _get_default_mapping_model_id(self):
        return self.env['efficy.mapping.model'].browse(self._context.get('active_id'))

    mapping_model_id = fields.Many2one(comodel_name='efficy.mapping.model', default=_get_default_mapping_model_id)
    record_ids = fields.One2many(comodel_name='efficy.pull.wizard.record', inverse_name='efficy_pull_wizard_id')

    def action_pull_records(self):
        for rec in self:
            rec.mapping_model_id.pull_records(rec.record_ids.mapped('key'))
        return {'type': 'ir.actions.act_window_close'}

    def action_fetch_records(self):
        for rec in self:
            keys = rec.mapping_model_id.fetch_records()
            print(keys)
            recs = self.env['efficy.pull.wizard.record'].create({'key': k} for k in keys)
            print(recs)
            rec.record_ids = recs.ids
            print(rec.record_ids)
        return True


class EfficyPullWizardRecord(models.TransientModel):
    _name = 'efficy.pull.wizard.record'
    _description = "Efficy Pull Wizard Record"

    key = fields.Char()
    efficy_pull_wizard_id = fields.Many2one(comodel_name='efficy.pull.wizard')

