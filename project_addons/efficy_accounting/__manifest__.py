{
    'name': 'Efficy Accounting',
    'author': 'Idealis Consulting',
    'website': 'https://www.idealisconsulting.com/',
    'summary': "Custom accounting Module for Efficy",
    'description': """
    """,
    'version': '14.0.0',
    'depends': [
        'account',
        'account_accountant',
        'base_vat',
        'efficy_connector',
    ],
    'data': [
        'views/account.xml',
        'views/company.xml',
        'views/partner.xml',
        'data/record_rules.xml',
        'security/ir.model.access.csv',

        'data/sequences.xml',

        'data/mapping_model_docu.xml',
        'data/mapping_model_comp.xml',
        'data/action.xml',
    ]
}
