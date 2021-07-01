import base64
import io
import logging
_logger = logging.getLogger(__name__)

import odoo.addons.documents_sorting.models.tag_functions as tag_functions

from odoo import api, fields, models


#link company to tag
class ResCompany(models.Model):
    _inherit = "res.company"
    bl_tag_id = fields.Many2one('documents.tag', string='Document tag', required=True)


class Document(models.Model):
    _inherit = "documents.document"

    # main function
    def process_doc(self):

        # get and set variables from system parameters
        poppler_path = ''
        tesseract_path = ''

        if self.env['ir.config_parameter'].sudo().get_param('documents_sorting.tesseract_path'):
            tesseract_path = self.env['ir.config_parameter'].sudo().get_param('documents_sorting.tesseract_path')
        if self.env['ir.config_parameter'].sudo().get_param('documents_sorting.poppler_path'):
            poppler_path = self.env['ir.config_parameter'].sudo().get_param('documents_sorting.poppler_path')

        dic_companies_TVA = {}

        # get company's TVA number and name
        companies = self.env['res.company'].search([])
        if companies:
            for company in companies:
                if company.vat:
                    tva_num = str(tag_functions.TVA_processing(company.vat)[0])
                    if tva_num:
                        dic_companies_TVA[tva_num] = company.bl_tag_id
                    else:
                        _logger.info("TVA number missing")


        # iterate through the different stored documents
        for record in self:
            text_doc = ''
            doc_binary = base64.b64decode(record.datas)
            # check if document is a PDF file
            if '%PDF' in str(doc_binary[0:20]):
                doc_pdf = io.BytesIO(doc_binary)
                text_doc = tag_functions.pdf_to_txt(doc_pdf)

                # check if PDF is not a scan or an image
                if len(text_doc) < 20:
                    f = open('file.pdf', 'wb')
                    f.write(doc_binary)
                    f.close()
                    images = tag_functions.pdf_to_image('file.pdf', poppler_path)
                    for image in images:
                        text_doc += tag_functions.image_to_text(image, tesseract_path)

            # check if document is a docx file
            elif tag_functions.binary_to_hex(doc_binary)[0:4] == ['50', '4B', '03', '04']:
                f = open('file.docx', 'wb')
                f.write(doc_binary)
                f.close()
                text_doc = tag_functions.docx_to_text('file.docx')

            # if not a docx or a PDF
            else:
                _logger.info("Unsupported format")

            # find the best tag related to the document
            if text_doc:
                match = set()
                list_TVA = tag_functions.TVA_processing(text_doc)

                for number in list_TVA:
                    if number in dic_companies_TVA:
                        match.add(number[0:10])
                if match:
                    if len(match) == 1:
                        record.tag_ids += dic_companies_TVA[match.pop()]

                    else:
                        _logger.info("Two potential companies found")
                else:
                    _logger.info("No correct TVA number found")
