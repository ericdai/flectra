# Part of Odoo S.A.,Flectra. See LICENSE file for full copyright and licensing details.
# This module is forward ported from Odoo v8 payment followup module.

{
    'name': 'Payment Follow-up Management',
    'version': '1.1',
    'category': 'Accounting & Finance',
    'summary': 'Payment Follow-up Management',
    'description': """
 Payment Follow is a simplified automated payment follow up tool, designed and
 developed based on market scenarios and user experiences. The tool is a boon
 for any businesses to regularly and automatically follow up payments from
 their customers or just anyone.
""",
    "author": "Odoo S.A., Flectra",
    'website': 'https://flectrahq.com',
    'depends': ['account', 'account_invoicing', 'mail', 'sales_team'],
    'data': [
        'security/account_followup_security.xml',
        'security/ir.model.access.csv',
        'data/account_followup_data.xml',
        'report/account_followup_report.xml',
        'views/account_followup_view.xml',
        'views/account_followup_customers.xml',
        'wizard/account_followup_print_view.xml',
        'views/report_followup.xml',
        'views/account_followup_reports.xml',
    ],
    'demo': ['demo/account_followup_demo.xml'],
    'installable': True,
    'auto_install': False,
}
