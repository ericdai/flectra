# Part of Odoo S.A.,Flectra See LICENSE file for full copyright and licensing details.

from flectra import api, fields, models, tools


class AccountFollowupStat(models.AbstractModel):
    _name = "account_followup.stat"
    _description = "Follow-up Statistics"
    _rec_name = 'partner_id'
    _auto = False

    partner_id = fields.Many2one('res.partner', 'Partner', readonly=True)
    date_move = fields.Date('First move', readonly=True)
    date_move_last = fields.Date('Last move', readonly=True)
    date_followup = fields.Date('Latest followup', readonly=True)
    followup_id = fields.Many2one('account_followup.followup.line',
                                  'Follow Ups', readonly=True,
                                  ondelete="cascade")
    balance = fields.Float('Balance', readonly=True)
    debit = fields.Float('Debit', readonly=True)
    credit = fields.Float('Credit', readonly=True)
    company_id = fields.Many2one('res.company', 'Company', readonly=True)
    blocked = fields.Boolean('Blocked', readonly=True)

    _order = 'date_move'

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        for arg in args:
            if arg[0] == 'period_id' and arg[2] == 'current_year':
                current_year = self.env['account.fiscalyear'].find()
                ids = current_year.read(['period_ids'])[0]['period_ids']
                args.append(['period_id', 'in', ids])
                args.remove(arg)
        return super(AccountFollowupStat, self).search(
            args, offset=0, limit=None, order=None, count=False)

    @api.model
    def read_group(self, domain, fields, groupby, offset=0,
                   limit=None, orderby=False, lazy=True):
        for arg in domain:
            if arg[0] == 'period_id' and arg[2] == 'current_year':
                current_year = self.env['account.fiscalyear'].find()
                ids = current_year.read(['period_ids'])[0]['period_ids']
                domain.append(['period_id', 'in', ids])
                domain.remove(arg)
        return super(AccountFollowupStat, self).read_group(
            domain, fields, groupby, offset=offset, limit=limit,
            orderby=orderby, lazy=lazy)

    @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self._cr, 'account_followup_stat')
        self._cr.execute("""
            create or replace view account_followup_stat as (
                SELECT
                    l.id as id,
                    l.partner_id AS partner_id,
                    min(l.date) AS date_move,
                    max(l.date) AS date_move_last,
                    max(l.followup_date) AS date_followup,
                    max(l.followup_line_id) AS followup_id,
                    sum(l.debit) AS debit,
                    sum(l.credit) AS credit,
                    sum(l.debit - l.credit) AS balance,
                    l.company_id AS company_id,
                    l.blocked as blocked
                FROM
                    account_move_line l
                    LEFT JOIN account_account a ON (l.account_id = a.id)
                WHERE
                    a.user_type_id IN (SELECT id FROM account_account_type
                    WHERE type = 'receivable') AND
                    l.full_reconcile_id is NULL AND
                    l.partner_id IS NOT NULL
                GROUP BY
                    l.id, l.partner_id, l.company_id, l.blocked
            )""")
