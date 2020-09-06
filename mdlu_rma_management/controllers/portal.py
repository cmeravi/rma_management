# -*- coding: utf-8 -*-
import datetime
from collections import OrderedDict
from dateutil.relativedelta import relativedelta
from werkzeug.exceptions import NotFound
from odoo import http
from odoo.http import request
from odoo.tools.translate import _

from odoo.addons.payment.controllers.portal import PaymentProcessing
from odoo.addons.portal.controllers.portal import get_records_pager, pager as portal_pager, CustomerPortal


class CustomerPortal(CustomerPortal):


    def _prepare_portal_layout_values(self):
        """ Add rma details to main account page """
        values = super(CustomerPortal, self)._prepare_portal_layout_values()
        partner = request.env.user.partner_id

        vendor_rma_count = request.env['product.return'].search_count([
            ('message_partner_ids', 'child_of', [partner.id]),
            ('product_return_type', '=', 'outgoing')
        ])
        customer_rma_count = request.env['product.return'].search_count([
            ('message_partner_ids', 'child_of', [partner.id]),
            ('product_return_type', '=', 'incoming')
        ])

        values.update({
            'vrma_count': vendor_rma_count,
            'crma_count': customer_rma_count,
        })
        return values

    @http.route(['/my/vrmas', '/my/vrmas/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_vrmas(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        RMA = request.env['product.return']

        domain = [
            ('message_partner_ids', 'child_of', [partner.id]),
            ('product_return_type', '=', 'outgoing')
        ]

        archive_groups = self._get_archive_groups('product.return', domain)
        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        searchbar_sortings = {
            'date': {'label': _('Newest'), 'order': 'create_date desc, id desc'},
            'name': {'label': _('Name'), 'order': 'name asc, id asc'},
            'status': {'label': _('Status'), 'state': 'state asc, create_date asc'},
        }
        searchbar_filters = {
            'all': {'label': _('All'), 'domain': []},
            'draft': {'label': _('New'), 'domain': [('state', '=', 'draft')]},
            'waiting_refund': {'label': _('Waiting for Credit'), 'domain': [('state', '=', 'waiting_refund')]},
            'done': {'label': _('Done'), 'domain': [('state', '=', 'done')]},
            'cancelled': {'label': _('Cancelled'), 'domain': [('state', '=', 'cancelled')]},
        }

        # default sort by value
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        # default filter by value
        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        archive_groups = self._get_archive_groups('product.return', domain)
        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        # pager
        account_count = RMA.search_count(domain)
        pager = portal_pager(
            url="/my/vrmas",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 'filterby': filterby},
            total=account_count,
            page=page,
            step=self._items_per_page
        )

        accounts = RMA.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['my_vrma_history'] = accounts.ids[:100]

        values.update({
            'accounts': accounts,
            'page_name': 'vrma',
            'pager': pager,
            'archive_groups': archive_groups,
            'default_url': '/my/vrmas',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby,
        })
        return request.render("mdlu_rma_management.portal_my_vrmas", values)

    @http.route(['/my/crmas', '/my/crmas/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_crmas(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        RMA = request.env['product.return']

        domain = [
            ('message_partner_ids', 'child_of', [partner.id]),
            ('product_return_type', '=', 'incoming')
        ]

        archive_groups = self._get_archive_groups('product.return', domain)
        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        searchbar_sortings = {
            'date': {'label': _('Newest'), 'order': 'create_date desc, id desc'},
            'name': {'label': _('Name'), 'order': 'name asc, id asc'},
            'status': {'label': _('Status'), 'state': 'state asc, create_date asc'},
        }
        searchbar_filters = {
            'all': {'label': _('All'), 'domain': []},
            'draft': {'label': _('New'), 'domain': [('state', '=', 'draft')]},
            'processing': {'label': _('RMA Processing'), 'domain': [('state', '=', 'processing')]},
            'done': {'label': _('Done'), 'domain': [('state', '=', 'done')]},
            'cancelled': {'label': _('Cancelled'), 'domain': [('state', '=', 'cancelled')]},
        }

        # default sort by value
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        # default filter by value
        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        archive_groups = self._get_archive_groups('product.return', domain)
        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        # pager
        account_count = RMA.search_count(domain)
        pager = portal_pager(
            url="/my/crmas",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 'filterby': filterby},
            total=account_count,
            page=page,
            step=self._items_per_page
        )

        accounts = RMA.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['my_crma_history'] = accounts.ids[:100]

        values.update({
            'accounts': accounts,
            'page_name': 'crma',
            'pager': pager,
            'archive_groups': archive_groups,
            'default_url': '/my/crmas',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby,
        })
        return request.render("mdlu_rma_management.portal_my_crmas", values)


    @http.route(['/my/rmas/<int:rma_id>'], type='http', auth="public", website=True)
    def portal_rma_page(self, rma_id, access_token=None, message=False, download=False, **kw):
        try:
            rma_sudo = self._document_check_access('product.return', rma_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # use sudo to allow accessing/viewing orders for public user
        # only if he knows the private token
        now = datetime.date.today()

        # Log only once a day
        if rma_sudo and request.session.get('view_rma_%s' % rma_sudo.id) != now and request.env.user.share and access_token:
            request.session['view_vrma_%s' % rma_sudo.id] = now
            body = _('RMA viewed by vendor')
            _message_post_helper(res_model='product.return', res_id=rma_sudo.id, message=body, token=rma_sudo.access_token, message_type='notification', subtype="mail.mt_note", partner_ids=rma_sudo.user_id.sudo().partner_id.ids)

        return_url = '/my/crmas'
        if 'outgoing' == rma_sudo.product_return_type:
            return_url = '/my/vrmas'

        values = {
            'rma': rma_sudo,
            'message': message,
            'token': access_token,
            'return_url': '/my/rmas',
            'bootstrap_formatting': True,
            'partner_id': rma_sudo.partner_id.id,
        }
        if rma_sudo.company_id:
            values['res_company'] = rma_sudo.company_id


        history = request.session.get('my_crma_history', [])
        if 'outgoing' == rma_sudo.product_return_type:
            history = request.session.get('my_vrma_history', [])

        values.update(get_records_pager(history, rma_sudo))

        return request.render('mdlu_rma_management.rma_portal_template', values)
