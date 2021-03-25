{
    'name': 'Efficy Connector',
    'author': 'Idealis Consulting',
    'website': 'https://www.idealisconsulting.com/',
    'summary': "Connector Module for Efficy",
    'description': """
    """,
    'version': '14.0.0',
    'depends': [
        # 'contacts',
        # 'mail',
        # 'account',
    ],
    'data': [
        'data/groups.xml',

        'views/views.xml',
        'views/mapping.xml',
        'views/res_company.xml',
        'security/ir.model.access.csv',

        'wizards/pull_record_wizard.xml',
    ]
}
