Automated tag attribution for documents
---------------------------------------

The objective of this module is to provide a new and automated way
to tag the invoices in "Documents" based on their VAT number scanned in the file selected.
To initialize the process, the user needs to link each company with a tag (Settings > Companies > Company selected > Document tag).

It works with PDF (image or text), DOCX and more if needed.

System parameters
---------------------------------
In order to the module to work properly, 3 system parameter variables need to be set:
     
- documents_sorting.poppler_path which requires the full path of the poppler file which is defined afterwards 
  (ex.g. C:\Users\Louis Berwart\PycharmProjects\pythonProject\CV_Project\poppler-21.03.0\Library\bin). **In Linux, this step is facultative**.
  
- documents_sorting.tesseract_path which requires the full path to the tesseract file which is also defined afterwards
  (ex.g. C:\Program Files\Tesseract-OCR\tesseract.exe)

Required downloads
---------------------------------
- requirements.txt

- https://github.com/UB-Mannheim/tesseract/wiki

- https://github.com/oschwartz10612/poppler-windows/releases/tag/v21.03.0


