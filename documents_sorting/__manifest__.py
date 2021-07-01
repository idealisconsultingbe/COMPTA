# -*- coding: utf-8 -*-
{
    'name': "Documents Sorting",
    'version': '1.0',
    'category': 'Documents',
    'summary': 'Add a company tag to the documents (invoices)',
    'description': """
    """,
    'depends': ['documents'],
    'data': [
        'views/documents_views.xml',
        'views/res_company_views.xml'
    ],
    'auto_install': False,
}
