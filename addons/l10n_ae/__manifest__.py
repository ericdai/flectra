# -*- coding: utf-8 -*-
# Part of Odoo,Flectra. See LICENSE file for full copyright and licensing details.

# Copyright (C) 2014 Tech Receptives, Flectra (<http://techreceptives.com>)

{
    'name': 'U.A.E. - Accounting',
    'author': 'Tech Receptives, Flectra',
    'website': 'http://www.techreceptives.com',
    'category': 'Localization',
    'description': """
United Arab Emirates accounting chart and localization.
=======================================================

    """,
    'depends': ['base', 'account'],
    'data': [
             'data/account_data.xml',
             'data/l10n_ae_chart_data.xml',
             'data/account_chart_template_data.yml',
    ],
}
