import pdfplumber
import pytesseract
from pdf2image import convert_from_path
import docx2txt
import re

def pdf_to_txt(doc_pdf):
    text_doc = ''
    with pdfplumber.open(doc_pdf) as pdf:
        pages = pdf.pages
        for idx, page in enumerate(pages):
            txt_page = page.extract_text(x_tolerance=1, y_tolerance=1)
            if txt_page:
                text_doc += txt_page
    return text_doc


def image_to_text(filename, tesseract_path):
    path = tesseract_path
    pytesseract.pytesseract.tesseract_cmd = path
    text = pytesseract.image_to_string(filename)
    return text


def pdf_to_image(filename, poppler_path):
    path = poppler_path
    images = convert_from_path(filename, poppler_path=path)
    return images


def binary_to_hex(doc_binary):
    out_hex = ['{:02X}'.format(b) for b in doc_binary]
    return out_hex


def docx_to_text(doc_docx):
    text = docx2txt.process(doc_docx)
    return text

def TVA_processing(text):
    text = text.replace(" ", '').replace(".", '').replace("-", '').replace("/", '')
    TVA = re.findall(r'[0-9]{10}', text)
    return TVA
