# Part of Odoo S.A.,Flectra See LICENSE file for full copyright and licensing details.

from lxml import etree
from flectra import models, api, fields, _
from flectra.exceptions import UserError
from flectra.tools.misc import formatLang
from functools import reduce


class Followup(models.Model):
    _name = 'account_followup.followup'
    _description = 'Account Follow-up'
    _rec_name = 'name'

    name = fields.Char(string="Name",
                       readonly=True, related='company_id.name')
    company_id = fields.Many2one(
        'res.company', 'Company', required=True,
        default=lambda s: s.env['res.company']._company_default_get(
            'account_followup.followup'))
    followup_line = fields.One2many('account_followup.followup.line',
                                    'followup_id', 'Follow-up', copy=True)

    _sql_constraints = [('company_uniq', 'unique(company_id)',
                         'Per Company only one follow-up  is allowed')]


class FollowupLine(models.Model):
    _name = 'account_followup.followup.line'
    _description = 'Follow-up Criteria'
    _order = 'delay'

    @api.multi
    def _get_default_template(self):
        try:
            return self.env.ref(
                'account_followup.email_template_account_followup_default').id
        except ValueError:
            return False

    name = fields.Char('Action Name', required=True)
    sequence = fields.Integer('Sequence',
                              help="Sequence number to display a "
                                   "list of follow-up lines.")
    followup_id = fields.Many2one('account_followup.followup', 'Follow Ups',
                                  required=True, ondelete="cascade")
    delay = fields.Integer('Days Overdue',
                           help="The number of days after the due date"
                                " of the invoice to wait before sending"
                                " the reminder.  Could be negative if you"
                                " want to send a polite alert beforehand.",
                           required=True)

    send_email = fields.Boolean('Send an Email',
                                help="When processing, it will send an email",
                                default=True)
    email_template_id = fields.Many2one('mail.template',
                                        'Email Template',
                                        ondelete='set null',
                                        default=_get_default_template)
    send_letter = fields.Boolean(
        'Send a Letter',
        help="When processing, it will print a letter",
        default=True)
    manual_action_note = fields.Text(
        'Action To Do',
        placeholder="e.g. Give a phone call, check with others , ...")
    manual_action = fields.Boolean(
        'Manual Action', default=False,
        help="When processing, it will set the manual action to be taken "
             "for that customer. ")
    manual_action_responsible_id = fields.Many2one('res.users',
                                                   'Assign a Responsible',
                                                   ondelete='set null')
    description = fields.Text(
        'Printed Message', translate=True,
        default="""
            Dear %(partner_name)s,

    Exception made if there was a mistake of ours, it seems that the
     following amount stays unpaid. Please, take appropriate measures
      in order to carry out this payment in the next 8 days.

    Would your payment have been carried out after this mail was sent,
     please ignore this message. Do not hesitate to contact
      our accounting department.

    Best Regards,
    """)

    _sql_constraints = [('days_uniq', 'unique(followup_id, delay)',
                         'Days of the follow-up levels must be different')]

    @api.multi
    def _is_valid_description(self):
        for line in self:
            if line.description:
                try:
                    line.description % {'partner_name': '', 'date': '',
                                        'user_signature': '',
                                        'company_name': ''}
                except:
                    return False
        return True

    _constraints = [
        (_is_valid_description,
         'Invalid description, use the right legend or %% if '
         'you want to use the percent character.', ['description']),
    ]


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.multi
    def _get_balance(self):
        for aml in self:
            aml.balance = aml.debit - aml.credit

    followup_date = fields.Date('Latest Follow-up', index=True)
    followup_line_id = fields.Many2one(
        'account_followup.followup.line', 'Follow-up Level',
        ondelete='restrict')  # restrict deletion of the followup line
    balance = fields.Float(compute='_get_balance',
                           string="Balance")  # 'balance' field is not the same


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.multi
    def write(self, vals):
        if vals.get("payment_responsible_id", False):
            for part in self:
                if part.payment_responsible_id != \
                        vals["payment_responsible_id"]:
                    # Find partner_id of user put as responsible
                    responsible_partner_id = self.env["res.users"].browse(
                        vals['payment_responsible_id']).partner_id.id
                    self.env["mail.thread"].message_post(
                        body=_("You became responsible to do the next "
                               "action for the payment follow-up of") +
                        " <b><a href='#id=" + str(part.id) +
                        "&view_type=form&model=res.partner'> " +
                        part.name + " </a></b>",
                        type='comment',
                        subtype="mail.mt_comment",
                        model='res.partner', res_id=part.id,
                        partner_ids=[responsible_partner_id])
        return super(ResPartner, self).write(vals)

    @api.model
    def fields_view_get(self, view_id=None, view_type='form',
                        toolbar=False, submenu=False):
        res = super(ResPartner, self).fields_view_get(view_id=view_id,
                                                      view_type=view_type,
                                                      toolbar=toolbar,
                                                      submenu=submenu)
        if view_type == 'form' and self.env.context.get('Followupfirst'):
            doc = etree.XML(res['arch'], parser=None, base_url=None)
            first_node = doc.xpath("//page[@name='followup_tab']")
            if first_node:
                root = first_node[0].getparent()
                root.insert(0, first_node[0])
            res['arch'] = etree.tostring(doc, encoding="utf-8")
        return res

    @api.multi
    def _get_latest_followup_details(self):
        company = False
        for partner in self:
            if not partner.company_id:
                company = self.env.user.company_id.id
            else:
                company = self.env['res.company'].browse(
                    partner.company_id.id).id
            amls = partner.unreconciled_aml_ids
            latest_date = latest_level = latest_days = False
            latest_level_without_lit = latest_days_without_lit = False
            for aml in amls:
                if (aml.company_id.id == company) and \
                        aml.followup_line_id and \
                        (not latest_days or
                            latest_days < aml.followup_line_id.delay):
                    latest_days = aml.followup_line_id.delay
                    latest_level = aml.followup_line_id.id
                if (aml.company_id.id == company) and \
                        (not latest_date or (aml.followup_date and
                                             latest_date < aml.followup_date)):
                    latest_date = aml.followup_date
                if (aml.company_id.id == company) and \
                        (not aml.blocked) and \
                        (aml.followup_line_id and
                            (not latest_days_without_lit or
                                latest_days_without_lit <
                                aml.followup_line_id.delay)):
                    latest_days_without_lit = aml.followup_line_id.delay
                    latest_level_without_lit = aml.followup_line_id.id
            partner.latest_followup_date = latest_date
            partner.latest_followup_level_id = latest_level
            partner.latest_followup_level_id_without_lit = \
                latest_level_without_lit

    @api.multi
    def _get_payment_rel_details(self):
        '''
        Function that computes values for the followup functional fields.
        Note that 'payment_amount_due'
        is similar to 'credit' field on res.partner
        except it filters on user's company.
        '''
        company = self.env.user.company_id
        current_date = fields.Date.today()
        for partner in self:
            worst_due_date = False
            amount_due = amount_overdue = 0.0
            for aml in partner.unreconciled_aml_ids:
                if (aml.company_id == company):
                    date_maturity = aml.date_maturity or aml.date
                    if not worst_due_date or date_maturity < worst_due_date:
                        worst_due_date = date_maturity
                    amount_due += aml.balance
                    if (date_maturity <= current_date):
                        amount_overdue += aml.balance
            partner.payment_amount_due = amount_due
            partner.payment_amount_overdue = amount_overdue
            partner.payment_earliest_due_date = worst_due_date

    @api.multi
    def _partner_manual_action(self, partner_ids):
        for partner in self.browse(partner_ids):
            # Check action: check if the action was not empty, if not add
            action_text = ""
            f_level = partner.latest_followup_level_id_without_lit
            action_note = f_level.manual_action_note
            if partner.payment_next_action:
                action_text = (partner.payment_next_action or '') + "\n" + \
                              (action_note or '')
            else:
                action_text = action_note or ''

            # Check date: only change when it did not exist already
            action_date = \
                partner.payment_next_action_date or \
                fields.Date.today()

            # Check responsible: if partner has not got a responsible already,
            #  take from follow-up
            responsible_id = False
            if partner.payment_responsible_id:
                responsible_id = partner.payment_responsible_id.id
            else:
                p = f_level.manual_action_responsible_id
                responsible_id = p and p.id or False
            partner.write({'payment_next_action_date': action_date,
                           'payment_next_action': action_text,
                           'payment_responsible_id': responsible_id})

    @api.multi
    def do_partner_print(self, data):
        # wizard_partner_ids are ids from special view, not from res.partner
        data['partner_ids'] = self.ids
        datas = {
            'ids': self.ids,
            'model': 'account_followup.followup',
            'form': data
        }
        return self.env.ref(
            'account_followup.action_report_followup').report_action(
            self, data=datas)

    @api.multi
    def do_button_print(self):
        assert (len(self.ids) == 1)
        company_id = self.env.user.company_id.id
        # search if the partner has accounting entries to print.
        # If not, it may not be present in the
        # psql view the report is based on, so we need to stop the user here.
        if not self.env['account.move.line'].search([
            ('partner_id', '=', self.ids[0]),
            ('account_id.user_type_id.type', '=', 'receivable'),
            ('full_reconcile_id', '=', False),
            ('company_id', '=', company_id),
            '|', ('date_maturity', '=', False),
            ('date_maturity', '<=', fields.Date.today()),
        ]):
            raise UserError(_('Error! \nThe partner does not have any '
                              'accounting entries to print in the overdue '
                              'report for the current company.'))
        self.message_post(body=_('Printed overdue payments report'))
        # build the id of this partner in the psql view. Could be replaced
        # by a search with [('company_id', '=', company_id),
        # ('partner_id', '=', ids[0])]
        wizard_partner_ids = [self.ids[0] * 10000 + company_id]

        followup_ids = self.env['account_followup.followup'].search(
            [('company_id', '=', company_id)])
        if not followup_ids:
            raise UserError(_('Error! \nThere is no followup plan '
                              'defined for the current company.'))
        data = {
            'date': fields.date.today(),
            'followup_id': followup_ids[0] and followup_ids[0].id,
        }
        # call the print overdue report on this partner
        return self.env['res.partner'].browse(
            wizard_partner_ids).do_partner_print(data)

    @api.multi
    def do_partner_mail(self):

        ctx = self.env.context.copy()
        ctx['followup'] = True
        # partner_ids are res.partner ids
        # If not defined by latest follow-up level, it will be
        # the default template if it can find it
        mtp = self.env['mail.template']
        unknown_mails = 0
        template = 'account_followup.email_template_account_followup_default'
        for partner in self:
            partners_to_email = [child for child in partner.child_ids if
                                 child.type == 'invoice' and child.email]
            if not partners_to_email and partner.email:
                partners_to_email = [partner]
            if partners_to_email:
                level = partner.latest_followup_level_id_without_lit
                for partner_to_email in partners_to_email:
                    if level and level.send_email and \
                            level.email_template_id and \
                            level.email_template_id.id:
                        level.email_template_id.with_context(ctx).send_mail(
                            partner_to_email.id)
                    else:
                        mail_template_id = self.env.ref(template).id
                        mtp.browse(mail_template_id).send_mail(
                            partner_to_email.id)
                if partner not in partners_to_email:
                    partner.message_post(body=_(
                        'Overdue email sent to %s' % ', '.join(
                            ['%s <%s>' % (partner.name, partner.email)
                             for partner in partners_to_email])))
            else:
                unknown_mails = unknown_mails + 1
                action_text = _("Email not sent because of email address of "
                                "partner not filled in")
                if partner.payment_next_action_date:
                    payment_action_date = min(fields.Date.today(),
                                              partner.payment_next_action_date)
                else:
                    payment_action_date = fields.Date.today()
                if partner.payment_next_action:
                    payment_next_action = \
                        partner.payment_next_action + \
                        " \n " + action_text
                else:
                    payment_next_action = action_text
                partner.with_context(ctx).write({
                    'payment_next_action_date': payment_action_date,
                    'payment_next_action': payment_next_action})
        return unknown_mails

    @api.multi
    def get_followup_table_html(self):
        """ Build the html tables to be included in emails send to partners,
            when reminding them their overdue invoices.
            :param ids: [id] of the partner for whom we are building the tables
            :rtype: string
        """
        account_followup_print = \
            self.env['report.account_followup.report_followup']
        assert len(self.ids) == 1
        partner = self.commercial_partner_id
        # copy the context to not change global context.
        # Overwrite it because _()
        # looks for the lang in local variable 'context'.
        # Set the language to use = the partner language
        followup_table = ''
        if partner.unreconciled_aml_ids:
            company = self.env.user.company_id
            current_date = fields.Date.today()
            final_res = account_followup_print._get_lines_with_partner(
                partner, company.id)

            for currency_dict in final_res:
                currency = currency_dict.get(
                    'line', [{
                        'currency_id': company.currency_id
                    }])[0]['currency_id']
                followup_table += '''
                <table border="2" width=100%%>
                <tr>
                    <td>''' + _("Invoice Date") + '''</td>
                    <td>''' + _("Description") + '''</td>
                    <td>''' + _("Reference") + '''</td>
                    <td>''' + _("Due Date") + '''</td>
                    <td>''' + _("Amount") + " (%s)" % (
                    currency.symbol) + '''</td>
                    <td>''' + _("Lit.") + '''</td>
                </tr>
                '''
                total = 0
                for aml in currency_dict['line']:
                    block = aml['blocked'] and 'X' or ' '
                    total += aml['balance']
                    strbegin = "<TD>"
                    strend = "</TD>"
                    date = aml['date_maturity'] or aml['date']
                    if date <= current_date and aml['balance'] > 0:
                        strbegin = "<TD><B>"
                        strend = "</B></TD>"
                    followup_table += \
                        "<TR>" + strbegin + str(aml['date']) + \
                        strend + strbegin + aml['name'] + \
                        strend + strbegin + \
                        (aml['ref'] or '') + \
                        strend + strbegin + \
                        str(date) + strend + strbegin + str(aml['balance']) + \
                        strend + strbegin + block + strend + \
                        "</TR>"

                total = reduce(lambda x, y: x + y['balance'],
                               currency_dict['line'], 0.00)

                total = formatLang(self.env, total, dp='Account',
                                   currency_obj=currency)
                followup_table += '''<tr> </tr>
                                </table>
                                <br>
                                <div align="right"> <B>
                                <font style="font-size: 14px;">''' + \
                                  _("Amount due") + ''' : %s
                                  </div>''' % (total)
        return followup_table

    @api.multi
    def action_done(self):
        return self.write({
            'payment_next_action_date': False, 'payment_next_action': '',
            'payment_responsible_id': False})

    @api.multi
    def _payment_earliest_date_search(self, operator, operand):
        args = [('payment_earliest_due_date', operator, operand)]
        company_id = self.env.user.company_id.id
        having_where_clause = ' AND '.join(
            map(lambda x: "(MIN(l.date_maturity) %s '%%s')" % (x[1]), args))
        having_values = [x[2] for x in args]
        having_where_clause = having_where_clause % (having_values[0])
        query = 'SELECT partner_id FROM account_move_line l ' \
                'WHERE account_id IN ' \
                '(SELECT id FROM account_account ' \
                'WHERE user_type_id IN ' \
                '(SELECT id FROM account_account_type ' \
                'WHERE type=\'receivable\')) AND l.company_id = %s ' \
                'AND l.full_reconcile_id IS NULL ' \
                'AND partner_id IS NOT NULL GROUP BY partner_id '
        query = query % (company_id)
        if having_where_clause:
            query += ' HAVING %s ' % (having_where_clause)
        self._cr.execute(query)
        res = self._cr.fetchall()
        if not res:
            return [('id', '=', '0')]
        return [('id', 'in', [x[0] for x in res])]

    @api.multi
    def _get_query(self, args, overdue_only=False):
        '''
        This function is used to build the query and arguments to use when
         making a search on functional fields
            * payment_amount_due
            * payment_amount_overdue
        Basically, the query is exactly the same except that for overdue there
        is an extra clause in the WHERE.

        :param args: arguments given to the search in the usual domain notation
        (list of tuples)
        :param overdue_only: option to add the extra argument to filter on
        overdue accounting entries or not
        :returns: a tuple with
            * the query to execute as first element
            * the arguments for the execution of this query
        :rtype: (string, [])
        '''
        company_id = self.env.user.company_id.id
        having_where_clause = ' AND '.join(
            map(lambda x: '(SUM(bal2) %s %%s)' % (x[1]), args))
        having_values = [x[2] for x in args]
        having_where_clause = having_where_clause % (having_values[0])
        overdue_only_str = overdue_only and 'AND date_maturity <= NOW()' or ''
        return ('''SELECT pid AS partner_id, SUM(bal2) FROM
                            (SELECT CASE WHEN bal IS NOT NULL THEN bal
                            ELSE 0.0 END AS bal2, p.id as pid FROM
                            (SELECT (debit-credit) AS bal, partner_id
                            FROM account_move_line l
                            WHERE account_id IN
                                    (SELECT id FROM account_account
                                    WHERE user_type_id IN (SELECT id
                                    FROM account_account_type
                                    WHERE type=\'receivable\'
                                    ))
                            %s AND full_reconcile_id IS NULL
                            AND company_id = %s) AS l
                            RIGHT JOIN res_partner p
                            ON p.id = partner_id ) AS pl
                            GROUP BY pid HAVING %s''') % (
            overdue_only_str, company_id, having_where_clause)

    @api.multi
    def _payment_due_search(self, operator, operand):
        args = [('payment_amount_due', operator, operand)]
        query = self._get_query(
            args, overdue_only=False)
        self._cr.execute(query)
        res = self._cr.fetchall()
        if not res:
            return [('id', '=', '0')]
        return [('id', 'in', [x[0] for x in res])]

    @api.multi
    def _payment_overdue_search(self, operator, operand):
        args = [('payment_amount_overdue', operator, operand)]
        query = self._get_query(
            args, overdue_only=True)
        self._cr.execute(query)
        res = self._cr.fetchall()
        if not res:
            return [('id', '=', '0')]
        return [('id', 'in', [x[0] for x in res])]

    unreconciled_aml_ids = fields.One2many(
        'account.move.line', 'partner_id',
        domain=['&', ('full_reconcile_id', '=', False),
                ('account_id.user_type_id.type', '=', 'receivable')])
    payment_note = fields.Text(
        'Customer Payment Promise', help="Payment Note",
        track_visibility="onchange", copy=False)
    payment_responsible_id = fields.Many2one(
        'res.users', ondelete='set null', string='Follow-up Responsible',
        help="Optionally you can assign a user to this field, "
             "which will make him responsible for the action.",
        track_visibility="onchange", copy=False)
    payment_next_action = fields.Text(
        'Schedule Action', copy=False,
        help="This is the next action to be taken.  It will automatically be "
             "set when the partner gets a follow-up level that requires a "
             "manual action. ",
        track_visibility="onchange")
    payment_next_action_date = fields.Date(
        'Next Action Date', copy=False,
        help="This is when the manual follow-up is needed. "
             "The date will be set to the current date when the partner "
             "gets a follow-up level that requires a manual action. "
             "Can be practical to set manually e.g. to see if he keeps "
             "his promises.")
    latest_followup_level_id = fields.Many2one(
        'account_followup.followup.line',
        compute='_get_latest_followup_details',
        string="Latest Follow-up Level",
        help="The maximum follow-up level",
        multi="latest")
    latest_followup_date = fields.Date(
        compute='_get_latest_followup_details', string="Latest Follow-up Date",
        help="Latest date that the follow-up level of the partner was changed",
        multi="latest")
    latest_followup_level_id_without_lit = fields.Many2one(
        'account_followup.followup.line',
        compute='_get_latest_followup_details',
        string="Latest Follow-up Level without litigation",
        help="The maximum follow-up level without taking into "
             "account the account move lines with litigation",
        multi="latest")
    payment_earliest_due_date = fields.Date(
        compute='_get_payment_rel_details', string="Worst Due Date",
        multi="followup", search='_payment_earliest_date_search')
    payment_amount_due = fields.Float(
        compute='_get_payment_rel_details', string="Amount Due",
        store=False, multi="followup", search='_payment_due_search')
    payment_amount_overdue = fields.Float(
        compute='_get_payment_rel_details', string="Amount Overdue",
        store=False, multi="followup", search='_payment_overdue_search')

    @api.multi
    def open_follow_ups(self):
        form_view = self.env.ref(
            'account_followup.res_partner_followup_form_view')
        return {
            'name': _('Follow Ups'),
            'res_model': 'res.partner',
            'res_id': self.id,
            'views': [(form_view.id, 'form'), ],
            'type': 'ir.actions.act_window',
        }


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    @api.multi
    def open_followup_level(self):
        res_ids = self.env['account_followup.followup'].search([])
        return {
            'type': 'ir.actions.act_window',
            'name': 'Payment Follow-ups',
            'res_model': 'account_followup.followup',
            'res_id': res_ids and res_ids[0].id or False,
            'view_mode': 'form,tree',
        }
