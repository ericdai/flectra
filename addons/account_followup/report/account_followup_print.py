# Part of Odoo S.A.,Flectra See LICENSE file for full copyright and licensing details.

import time
from collections import defaultdict
from flectra import api, fields, models, _
from flectra.exceptions import UserError


class ReportRappel(models.AbstractModel):
    _name = 'report.account_followup.report_followup'

    def _get_lines(self, stat_by_partner_line):
        partner = []
        company = []
        for partner_line in stat_by_partner_line:
            partner.append(partner_line.partner_id.id)
            company.append(partner_line.company_id.id)
        return self._get_lines_with_partner(partner, company)

    def _get_lines_with_partner(self, partner, company_id):
        moveline_obj = self.env['account.move.line']
        moveline_ids = False
        total = 0
        if isinstance(partner, list):
            moveline_ids = moveline_obj.search([
                ('partner_id', 'in', partner),
                ('account_id.user_type_id.type', '=', 'receivable'),
                ('full_reconcile_id', '=', False),
                ('company_id', 'in', company_id),
                '|', ('date_maturity', '=', False),
                ('date_maturity', '<', fields.Date.today()),
            ])
        else:
            moveline_ids = moveline_obj.search([
                ('partner_id', '=', partner.id),
                ('account_id.user_type_id.type', '=', 'receivable'),
                ('full_reconcile_id', '=', False),
                ('company_id', '=', company_id),
                '|', ('date_maturity', '=', False),
                ('date_maturity', '<', fields.Date.today()),
            ])

        lines_per_currency = defaultdict(list)
        for line in moveline_ids:
            currency = line.currency_id or line.company_id.currency_id
            line_data = {
                'name': line.move_id.name,
                'ref': line.ref,
                'date': line.date,
                'date_maturity': line.date_maturity,
                'balance':
                    line.amount_currency if currency !=
                    line.company_id.currency_id else
                    line.debit - line.credit,
                'blocked': line.blocked,
                'currency_id': currency,
            }
            total = total + line_data['balance']
            lines_per_currency[currency].append(line_data)

        return [{'total': total,
                 'line': lines,
                 'currency': currency} for currency, lines in
                lines_per_currency.items()]

    def _get_text(self, stat_line, followup_id):
        fp_obj = self.env['account_followup.followup']
        fp_line = fp_obj.browse(followup_id).followup_line
        if not fp_line:
            raise UserError(_('Error! \n '
                              'The followup plan defined for the current '
                              'company does not have any followup action.'))
        # the default text will be the first fp_line in
        #  the sequence with a description.
        default_text = ''
        li_delay = []
        for line in fp_line:
            if not default_text and line.description:
                default_text = line.description
            li_delay.append(line.delay)
        li_delay.sort(reverse=True)
        # look into the lines of the partner that
        # already have a followup level,
        #  and take the description of the higher level
        # for which it is available
        partner_line_ids = self.env['account.move.line'].search(
            [('partner_id', '=', stat_line.partner_id.id),
             ('full_reconcile_id', '=', False),
             ('company_id', '=', stat_line.company_id.id),
             ('blocked', '=', False),
             ('debit', '!=', False),
             ('account_id.user_type_id.type', '=', 'receivable'),
             ('followup_line_id', '!=', False)])
        partner_max_delay = 0
        partner_max_text = ''
        for i in partner_line_ids:
            if i.followup_line_id.delay > partner_max_delay and \
                    i.followup_line_id.description:
                partner_max_delay = i.followup_line_id.delay
                partner_max_text = i.followup_line_id.description
        text = partner_max_delay and partner_max_text or default_text
        if text:
            lang_obj = self.env['res.lang']
            lang_ids = lang_obj.search(
                [('code', '=', stat_line.partner_id.lang)], limit=1)
            date_format = lang_ids and lang_ids.date_format or '%Y-%m-%d'
            text = text % {
                'partner_name': stat_line.partner_id.name,
                'date': time.strftime(date_format),
                'company_name': stat_line.company_id.name,
                'user_signature': self.env.user.signature or '',
            }
        return text

    def _ids_to_objects(self, ids):
        all_lines = []
        for line in self.env['account_followup.stat.by.partner'].browse(ids):
            if line not in all_lines:
                all_lines.append(line)
        return all_lines

    @api.model
    def get_report_values(self, docids, data=None):
        model = self.env['account_followup.sending.results']
        ids = self.env.context.get('active_ids') or False
        docs = model.browse(ids)
        return {
            'doc_ids': docids,
            'doc_model': model,
            'data': data and data['form'] or {},
            'docs': docs,
            'time': time,
            'getLines': self._get_lines,
            'get_text': self._get_text,
            'ids_to_objects': self._ids_to_objects,

        }
