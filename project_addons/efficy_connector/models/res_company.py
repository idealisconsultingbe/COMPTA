from odoo import models, fields
import json


class ResCompany(models.Model):
    _inherit = 'res.company'

    efficy_database_url = fields.Char(groups="efficy_connector.group_efficy_admin", help="Efficy Database URL (include http(s))")
    efficy_database_endpoint = fields.Char(compute="_compute_efficy_database_endpoint")
    efficy_database_user = fields.Char(groups="efficy_connector.group_efficy_admin")
    efficy_database_apikey = fields.Char(groups="efficy_connector.group_efficy_admin")
    efficy_database_password = fields.Char(groups="efficy_connector.group_efficy_admin")
    efficy_database_headers = fields.Char(compute="_compute_efficy_database_headers", groups="efficy_connector.group_efficy_admin")
    efficy_database_cookie = fields.Char(groups="efficy_connector.group_efficy_admin")
    efficy_last_sync_date = fields.Datetime()
    # efficy_database_custom_headers = fields.Char(compute="_compute_efficy_database_headers", groups="efficy_connector.group_efficy_admin")

    def _compute_efficy_database_endpoint(self):
        for rec in self:
            rec.efficy_database_endpoint = ("%s/crm/json" % rec.efficy_database_url) if rec.efficy_database_url else ""

    def _compute_efficy_database_headers(self):
        for rec in self:
            rec.efficy_database_headers = json.dumps({
                "X-Efficy-User": rec.efficy_database_user or '',
                "X-Efficy-Pwd": rec.efficy_database_password or '',
                "X-Efficy-ApiKey": rec.efficy_database_apikey or '',
                "Cookie": rec.efficy_database_cookie or '',
            })
