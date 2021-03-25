from odoo import models, fields, api
from odoo.tools import safe_eval
from odoo.exceptions import UserError
from pprint import pprint
from . import integration
import re
from time import time
import requests
from datetime import datetime
import json
import logging

_logger = logging.getLogger(__name__)


class EfficyMappingModel(models.Model):
    _name = 'efficy.mapping.model'
    _description = "Maps an efficy entity and its relations to odoo models"

    name = fields.Char()
    odoo_model_name = fields.Char()
    efficy_entity = fields.Char(required=True)
    efficy_category_ids = fields.One2many(comodel_name='efficy.category', inverse_name='mapping_model_id')
    efficy_detail_ids = fields.One2many(comodel_name='efficy.detail', inverse_name='mapping_model_id')
    mapping_field_ids = fields.One2many(comodel_name='efficy.mapping.field', inverse_name='mapping_model_id')
    company_id = fields.Many2one(comodel_name='res.company', default=lambda self: self.env.company)
    endpoint = fields.Char(related='company_id.efficy_database_endpoint')
    headers = fields.Char(related='company_id.efficy_database_headers')

    def name_get(self):
        return [(rec.id, "%s (%s => %s)" % (rec.name, rec.efficy_entity, rec.odoo_model_name)) for rec in self]

    def action_pull_records(self):
        return {
            'name': 'Pull Records',
            'res_model': 'efficy.pull.wizard',
            'view_mode': 'form',
            'target': 'new',
            'type': 'ir.actions.act_window',
            'binding_model_id': self.env['ir.model.data'].xmlid_to_res_id('efficy_connector.model_efficy_mapping_model')
        }

    def action_pull_all_records(self):
        self.pull_records_batch(self.fetch_records(), limit=10000)

    @api.model
    def json_request(self, payload):

        headers = self.env.company.efficy_database_headers
        endpoint = self.env.company.efficy_database_endpoint

        if not headers or not endpoint:
            raise UserError("Please configure the endpoint and the headers on the company's settings")

        if not payload:
            raise UserError("No payload provided to request")

        _logger.info("Request sent")
        _logger.debug("Request payload : %s" % payload)
        try:
            start = time()
            ans = requests.get(url=endpoint, json=payload, headers=json.loads(headers))
            dic = ans.json()
            _logger.info("Request took %s sec" % (time() - start))
        except Exception:
            _logger.warning("Error requesting records")
            raise UserError("Error requesting records")

        if 'Set-Cookie' in ans.headers:
            _logger.debug("Update Efficy cookie : %s => %s" % (self.env.context.get('efficy-cookie'), ans.headers['Set-Cookie']))
            # self.env.context.set('efficy-cookie', ans.headers['Set-Cookie'])
            self.env.company.efficy_database_cookie = ans.headers['Set-Cookie']

        return dic

    # @api.model
    # def json_parse(self, json_ans):
    #
    #     if not isinstance(json_ans, dict):
    #         try:
    #             json_ans = json_ans.json()
    #         except:
    #             raise UserError("Json answer is not a valid dict")
    #
    #     result = {}
    #
    #     for a in json_ans:
    #         if a['@name'] in ['consult']:
    #             key = a['key']
    #             for f in a['@func']:
    #                 func = f['@name']
    #                 data = f['#result']['#data']
    #                 result.setdefault(key, {}).setdefault(func, data)
    #         if a['@name'] in ['api']:
    #             for f in a['@func']:
    #                 key = f['param1']
    #                 func = f['@name']
    #                 data = f['#result']['#data']
    #                 result.setdefault(key, {}).setdefault(func, data)
    #
    #     return result

    def pull_records_batch(self, keys, size=100, limit=0, skip=False):
        if limit:
            del keys[limit:]
        for i in range(0, len(keys), size):
            _logger.info("Processed %s records out of %s" % (i, len(keys)))
            self.pull_records(keys[i: i + size], skip=skip)
        _logger.info("Processed %s records out of %s" % (len(keys), len(keys)))

    def pull_records(self, keys, skip=False):
        self.ensure_one()

        keys = [keys] if isinstance(keys, int) else keys

        payload = [{
            "@name": 'edit',
            "entity": self.efficy_entity,
            "key": k,
            "@func": [{"@name": "master"}] +
                     [{"@name": "category", "category": categ.name} for categ in self.efficy_category_ids] +
                     [{"@name": "detail", "detail": detail.name} for detail in self.efficy_detail_ids],
        } for k in keys]

        _logger.info("Requesting %s records on entity %s" % (len(keys), self.efficy_entity))
        ans = self.json_request(payload)

        _logger.info("Parsing data of %s requests" % len(ans))

        existing_records = self.sudo().env[self.odoo_model_name].search([('efficy_entity', '!=', False), ('efficy_key', '!=', False)])
        create_recs = []
        created_records = []
        updated_records = []
        original_env = self.env
        for x in ans:
            self.env = original_env
            try:
                _logger.debug("Got request answer : %s" % x)
                if x == '#error' or x.get('#error', False):
                    _logger.info("Request error : %s" % x.get('#error', False))
                    continue
                assert x['entity'] == self.efficy_entity
                record = existing_records.filtered(lambda i: i.efficy_key == str(x['key']) and i.efficy_entity == x['entity'])
                vals = {}
                for y in x['@func']:

                    if y['@name'] in ['master', 'category']:
                        if not y.get('#result', {}).get('#data'):
                            continue
                        data = y['#result']['#data'][0]
                        for mapping_field in self.mapping_field_ids.filtered(lambda i: i.efficy_category_id.name == y.get('category', False) and not i.efficy_detail_id):
                            mapping_field.env = self.env
                            res = mapping_field.mapping(data.get(mapping_field.efficy_field_name, None))
                            if isinstance(res, models.Model):
                                self.env = res.env
                            if mapping_field.odoo_field:
                                vals[mapping_field.odoo_field.name] = res

                    if y['@name'] in ['detail']:
                        if not y.get('#result', {}).get('#data'):
                            continue
                        detail = self.efficy_detail_ids.filtered(lambda i: i.name == y['detail']).ensure_one()
                        dataset = y['#result']['#data']
                        vals[detail.odoo_relation_field.name] = []
                        record[detail.odoo_relation_field.name] = False
                        for data in dataset:
                            vals_detail = {'efficy_entity': detail.name}
                            for mapping_field in self.mapping_field_ids.filtered(lambda i: i.efficy_detail_id.name == y['detail'] and i.odoo_field):
                                res = mapping_field.mapping(data.get(mapping_field.efficy_field_name, None))
                                if mapping_field.odoo_field:
                                    vals_detail[mapping_field.odoo_field.name] = res
                            existing = False
                            if 'efficy_key' in vals_detail:
                                existing = self.env[detail.odoo_model_name].search([('efficy_entity', '=', detail.name), ('efficy_key', '=', vals_detail['efficy_key'])])
                                if existing:
                                    existing.write(vals_detail)
                            if detail.odoo_relation_field.ttype in ['one2many', 'many2many']:
                                vals[detail.odoo_relation_field.name].append([(4, x.id, 0) for x in existing] if existing else (0, 0, vals_detail))
                            if detail.odoo_relation_field.ttype in ['many2one']:
                                vals[detail.odoo_relation_field.name] = existing.id or existing.create(vals_detail).id

                if not vals:
                    _logger.info("No data to import from %s %s, skipped" % (x['entity'], x['key']))
                    continue
                vals.update({
                    'efficy_entity': x['entity'],
                    'efficy_key': str(x['key']),
                    'efficy_mapping_model_id': self.id,
                    'active': True
                })
                for key, value in dict(vals).items():
                    if not value:
                        del vals[key]

                try:
                    if record:
                        _logger.debug("Write on record %s vals %s" % (record, vals))
                        record.write(vals)
                        updated_records.append((record, record.efficy_ref))
                    else:
                        # create_recs.append(vals)
                        _logger.debug("Create recs : %s" % vals)
                        self.env[self.odoo_model_name].create(vals)
                except Exception as e:
                    # import ipdb; ipdb.set_trace()
                    _logger.warning("Error on record : %s" % str(e))
                    if not skip:
                        raise UserError("Error on record : %s" % str(e))

            except SkipRecordException:
                _logger.info("Skipped record : %s" % x['key'])

        # _logger.debug("Create recs : %s" % create_recs)
        # try:
        #     created_records.append(self.env[self.odoo_model_name].create(create_recs))
        # except Exception as e1:
        #     for create_rec in create_recs:
        #         try:
        #             self.env[self.odoo_model_name].create(create_rec)
        #         except Exception as e2:
        #             _logger.error("Failed create record for %s\n Error : %s" % (create_rec, str(e2)))
        #             import ipdb; ipdb.set_trace()
        #     raise e1
        #
        # return {'create_records': created_records, 'updated_records': updated_records}

    def fetch_records_invoices_2021_BE(self):
        self.ensure_one()

        if not self.headers or not self.endpoint:
            raise UserError("Please configure the endpoint and the headers on the company's settings")

        payload = [{
            "@name": "api",
            "@func": [{
                "@name": "entitylist",
                "entity": self.efficy_entity,
                "active": True,
                "opened": True,
            }]
        }]
        ans = requests.get(url=self.endpoint, json=payload, headers=json.loads(self.headers))
        ans = json.loads(ans.text.replace('\x00', ''))
        key_field = self.mapping_field_ids.filtered(lambda x: x.odoo_field.name == 'efficy_key' and not x.efficy_detail_id).efficy_field_name
        _logger.info("Using key field %s" % key_field)
        keys = [a[key_field] for a in ans[0]['@func'][0]['#result']['#data'] if '2021' in a['REFERENCE'].split('-')]
        _logger.info("Fetched %s keys on entity %s" % (len(keys), self.efficy_entity))

        time.sleep(5)

        payload = [{
            "@name": "api",
            "@func": [{
                "@name": "entitylist",
                "entity": self.efficy_entity,
                "active": True,
                "opened": False,
            }]
        }]
        ans = requests.get(url=self.endpoint, json=payload, headers=json.loads(self.headers))
        ans = json.loads(ans.text.replace('\x00', ''))
        key_field = self.mapping_field_ids.filtered(lambda x: x.odoo_field.name == 'efficy_key' and not x.efficy_detail_id).efficy_field_name
        _logger.info("Using key field %s" % key_field)
        keys += [a[key_field] for a in ans[0]['@func'][0]['#result']['#data'] if '2020' in a['REFERENCE'].split('-')]
        _logger.info("Fetched %s keys on entity %s" % (len(keys), self.efficy_entity))

        return keys

    def fetch_records(self):
        self.ensure_one()

        if not self.headers or not self.endpoint:
            raise UserError("Please configure the endpoint and the headers on the company's settings")

        payload = [{
            "@name": "api",
            "@func": [{
                "@name": "entitylist",
                "entity": self.efficy_entity,
                "active": True,
                "opened": True,
            }]
        }]
        ans = requests.get(url=self.endpoint, json=payload, headers=json.loads(self.headers))
        ans = json.loads(ans.text.replace('\x00', ''))
        key_field = self.mapping_field_ids.filtered(lambda x: x.odoo_field.name == 'efficy_key' and not x.efficy_detail_id).efficy_field_name
        _logger.info("Using key field %s" % key_field)
        # keys = [(a[key_field], a['D_CHANGE']) for a in ans[0]['@func'][0]['#result']['#data'] if datetime.strptime(a['D_CHANGE'], "%Y-%m-%dT%H:%M:%S.000Z") <= datetime(year=2021, month=1, day=1)]
        keys = [(a[key_field], a['D_CHANGE']) for a in ans[0]['@func'][0]['#result']['#data']]
        _logger.info("Fetched %s keys on entity %s" % (len(keys), self.efficy_entity))

        return keys

    # def fetch_records_query(self):


class EfficyMappingField(models.Model):
    _name = 'efficy.mapping.field'
    _description = "Handles mapping and translating data from efficy fields to odoo fields"
    _order = 'sequence'

    active = fields.Boolean(default=True)
    sequence = fields.Integer()
    mapping_model_id = fields.Many2one(comodel_name='efficy.mapping.model')
    odoo_model_name = fields.Char(compute='_compute_odoo_model_name')
    odoo_field = fields.Many2one(comodel_name='ir.model.fields')
    mapping_regex = fields.Char(default="(.*)")
    mapping_selection_ids = fields.One2many(comodel_name='efficy.mapping.selection', inverse_name='efficy_mapping_field_id')
    mapping_function = fields.Selection([
        ('copy', 'Copy'),
        ('default', "Default Value"),
        ('search', "Search"),
        ('create', "Create"),
        ('get', "Get id or pull from Key"),
        ('skip', "Skip"),
        ('env', "Environment"),
        ('lookup', "Lookup"),
        ('product_family', "Product Family"),
        ('get_move_line', "get move line"),
    ], default='copy')
    mapping_parameter = fields.Char()
    mapping_summary = fields.Html(compute='_compute_mapping_summary')
    efficy_category_id = fields.Many2one(comodel_name='efficy.category')
    parent_detail_ids = fields.One2many(related='mapping_model_id.efficy_detail_ids', string="Parent Details")
    efficy_detail_id = fields.Many2one(comodel_name='efficy.detail')
    efficy_field_name = fields.Char()
    efficy_field_label = fields.Char()
    efficy_field_type = fields.Selection([
        ('A', '? (A)'),
        ('D', 'Date (D)'),
        ('I', 'Integer (I)'),
        ('L', 'Boolean (L)'),
        ('N', "Numeric (N)"),
        ('M', "Memo (M)"),
        ('B', "? (B)"),
        ('T', "? (T)"),
        ('S', "? (S)"),
        ('H', "? (H)"),
    ])

    @api.constrains('mapping_regex')
    def _verify_regex(self):
        for rec in self:
            try:
                re.compile(rec.mapping_regex)
            except Exception as e:
                raise UserError("Bad regex: %s" % str(e))

    # @api.constrains('mapping_parameter')
    # def _verify_parameter(self):
    #     for rec in self.filtered(lambda x: x.mapping_function in ['search', 'name_create', 'get']):
    #         if rec.mapping_function in ['search', 'name_create', 'get']:
    #             try:
    #                 safe_eval.safe_eval(rec.mapping_parameter)
    #             except Exception as e:
    #                 raise UserError("Bad domain: %s" % str(e))

    def _compute_mapping_summary(self):
        for rec in self:
            txt = "efficy_value > "
            txt += '<b>regex</b> > ' if rec.mapping_regex != '(.*)' else ''
            txt += '<b>mapping</b> > ' if rec.mapping_selection_ids else ''
            txt += '<b>%s</b>' % rec.mapping_function
            txt += '(params)' if rec.mapping_parameter else ''
            txt += ' > odoo_field'
            rec.mapping_summary = txt

    @api.onchange('odoo_field')
    def _onchange_odoo_field(self):
        for rec in self:
            if rec.odoo_field.related:
                raise UserError("This field is a related to %s. Please use the original field" % rec.odoo_field.related)

    def _compute_odoo_model_name(self):
        for rec in self:
            rec.odoo_model_name = rec.efficy_detail_id.odoo_model_name if rec.efficy_detail_id else rec.mapping_model_id.odoo_model_name

    def mapping(self, data):

        if data:
            regex_match = re.search(r'%s' % self.mapping_regex, str(data))
            if not regex_match:
                # raise UserError("Catching group does not match : %s %s" % (data, self.mapping_regex))
                return
            try:
                data = regex_match.group(1)
            except IndexError:
                raise UserError("No catching group to match : %s" % (self.mapping_regex))

        data = self.mapping_selection_ids.map(data)

        f = self.mapping_function

        if f == 'copy':
            return data

        if f == 'skip':
            raise SkipRecordException

        if f == 'default':
            return int(self.mapping_parameter) if self.mapping_parameter.isdigit() else self.mapping_parameter

        if f == 'search':
            domain = safe_eval.safe_eval(self.mapping_parameter, {'data': data})
            return self.env[self.odoo_field.relation].search(domain, limit=1).id

        if f == 'create':
            rec = self.env[self.odoo_field.relation].search([(self.mapping_parameter, '=', data)], limit=1)
            if self.odoo_field.ttype in ['one2many', 'many2many']:
                return [(4, rec.id, 0) if rec else (0, 0, {self.mapping_parameter: data})]
            if self.odoo_field.ttype in ['many2one']:
                return rec.id or rec.create({self.mapping_parameter: data}).id

        if f == 'env':
            if self.mapping_parameter == 'company':
                ans = self.with_company(int(data)).with_context(allowed_company_ids=[int(data)])
                return ans

        if f == 'get':
            mapping_model = self.env['efficy.mapping.model'].browse(int(self.mapping_parameter))
            record = self.env[mapping_model.odoo_model_name].search([
                ('name', '=', mapping_model.name),
                ('efficy_key', '=', data),
            ], limit=1)
            record = record or mapping_model.pull_records(data)
            if not record:
                raise Exception
            return record

        if f == 'product_family':
            product_family = self.get_product_family(data)
            rec = self.env[self.odoo_field.relation].search([('name', '=', product_family)], limit=1)
            return rec.id or rec.create({'name': product_family}).id

        if f == 'get_move_line':
            return self.get_move_line(data)


class EfficyMappingSelection(models.Model):
    _name = 'efficy.mapping.selection'
    _description = "Maps values one by one"

    odoo_value = fields.Char()
    efficy_value = fields.Char()
    efficy_mapping_field_id = fields.Many2one(comodel_name='efficy.mapping.field')

    def map(self, value):
        if not self:
            return value
        for rec in self:
            if re.search(rec.efficy_value or '', value or ''):
                _logger.debug("mapped selection %s to %s" % (value, rec.odoo_value))
                return rec.odoo_value
        raise UserError("value %s not found in mapping selection of %s" % (value, self.efficy_mapping_field_id.efficy_field_name))


class EfficyCategory(models.Model):
    _name = 'efficy.category'
    _description = "Efficy Category"

    name = fields.Char()
    mapping_model_id = fields.Many2one(comodel_name='efficy.mapping.model')


class EfficyDetail(models.Model):
    _name = 'efficy.detail'
    _description = "Efficy Detail"

    mapping_model_id = fields.Many2one(comodel_name='efficy.mapping.model')
    name = fields.Char(required=True)
    odoo_model_name = fields.Char(required=True)
    parent_odoo_model_name = fields.Char(related='mapping_model_id.odoo_model_name', string="Parent Odoo Model")
    odoo_relation_field = fields.Many2one(comodel_name='ir.model.fields')

    def name_get(self):
        return [(rec.id, "%s on %s" % (rec.name, rec.odoo_relation_field.name)) for rec in self]


class SkipRecordException(Exception):
    pass

