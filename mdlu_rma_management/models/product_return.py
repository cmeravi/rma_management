# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError, AccessError
from datetime import datetime, timedelta, date
import odoo.addons.decimal_precision as dp
from odoo.tools.misc import formatLang

SOURCE_LOCATION_DOMAINS = {
    'incoming': [('active', '=', True), ('usage', '=', 'customer')],
    'outgoing': [('active', '=', True), ('usage', '=', 'internal')],
}

DESTINATION_LOCATION_DOMAINS = {
    'incoming': [('active', '=', True), ('usage', '=', 'internal')],
    'outgoing': [('active', '=', True), ('usage', '=', 'supplier')],
}

PARTNER_DOMAINS = {
    'incoming': [('customer', '=', True)],
    'outgoing': [('supplier', '=', True)],
}

SOURCE_ORDER = {
    'incoming': 'sale_order_id',
    'outgoing': 'purchase_id',
}

SOURCE_LINE_MODEL = {
    'incoming': 'sale.order.line',
    'outgoing': 'purchase.order.line',
}

RMA_PRODUCT_TYPE = {
    'incoming': [('sale_ok', '=', True)],
    'outgoing': [('purchase_ok', '=', True)],
}

class ProductReturn(models.Model):
    _name = "product.return"
    _description = "RMA"
    _order = "name desc"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    @api.depends("return_line_ids.price_total")
    def _amount_all(self):
        """ Compute the total amounts of the Return. """

        for return_order in self:
            return_order.amount_total = sum(return_order.return_line_ids.mapped('price_total'))

    #get a count of how many pickings are associated with the RMA
    @api.multi
    def _compute_picking_ids(self):
        for rma in self:
            rma.delivery_count = len(rma.picking_ids.filtered(lambda pick: pick.state != 'cancel'))

    @api.multi
    def _compute_sale_orders(self):
        for rma in self:
            rma.sale_count = len(rma.sale_ids)

    @api.multi
    def _compute_purchase_orders(self):
        for rma in self:
            rma.purchase_count = len(rma.purchase_ids)

    def _edit_return_type(self):
        for rec in self:
            if rec.product_return_type in ['incoming', 'outgoing']:
                rec.edit_return_type = False



    @api.model
    def _get_return_type(self):
        return_type = self.product_return_type
        if not return_type:
            return_type = self._context.get('product_return_type')
        return return_type

    #Set Domains based on RMA Type
    @api.onchange('partner_id','product_return_type')
    def set_partner_domain(self):
        return_type = self._get_return_type()
        domain = PARTNER_DOMAINS[return_type] if return_type else []
        partner_ids = self.env['res.partner'].search(domain).mapped('id')
        return {'domain':{'partner_id': [('id','in',partner_ids)],},}

    @api.onchange('source_location_id','product_return_type')
    def set_source_domain(self):
        return_type = self._get_return_type()
        domain = SOURCE_LOCATION_DOMAINS[return_type] if return_type else []
        location_ids = self.env['stock.location'].search(domain).mapped('id')
        return {'domain':{'source_location_id': [('id','in',location_ids)],},}

    @api.onchange('destination_location_id','product_return_type')
    def set_destination_domain(self):
        return_type = self._get_return_type()
        domain = DESTINATION_LOCATION_DOMAINS[return_type] if return_type else []
        location_ids = self.env['stock.location'].search(domain).mapped('id')
        return {'domain':{'destination_location_id': [('id','in',location_ids)],},}


    edit_return_type = fields.Boolean(compute='_edit_return_type', default=True)
    product_return_type = fields.Selection([('incoming', 'Customer'), ('outgoing', 'Vendor')], string="Return Type", required=True,
        readonly=True, states={'draft': [('readonly', False)]},
        help=" * Customer Returns are incoming shipments that the customer is returning to us for refund, replacement, or credit."
             " * Vendor Returns are outgoing shipments that we are sending back to the vendor for refund, replacement, or credit")
    name = fields.Char(string='Return Reference', required=True, copy=False, readonly=True, index=True, default='New')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('processing', 'Processing'),
        ('followup', 'Followup'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')],
        string='Status', default='draft', track_visibility=True)
    partner_id = fields.Many2one('res.partner', string='Partner', required=True,readonly=True, states={'draft': [('readonly', False)]})
    reference = fields.Char('RMA Number', readonly=True, states={'draft': [('readonly', False)]})
    order_date = fields.Datetime('Order Date', required=True, readonly=True, states={'draft': [('readonly', False)]}, default=fields.Datetime.now)
    reason_return = fields.Text('Reason for Return', readonly=True, states={'draft': [('readonly', False)]})
    purchase_id = fields.Many2one('purchase.order', string='Source Purchase Order')
    sale_order_id = fields.Many2one('sale.order', string='Source Sale Order')

    source_location_id = fields.Many2one('stock.location', string='Source Location', required=True, readonly=True, states={'draft': [('readonly', False)]})
    destination_location_id = fields.Many2one('stock.location', string='Destination Location', required=True, readonly=True, states={'draft': [('readonly', False)]})

    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.user.company_id, readonly=True, states={'draft': [('readonly', False)]})
    return_line_ids = fields.One2many('product.return.line', 'return_id', string='Return Lines', readonly=True, states={'draft': [('readonly', False)]})
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_amount_all', track_visibility='always')
    currency_id = fields.Many2one("res.currency", related='company_id.currency_id', string="Currency", readonly=True, required=True)

    invoice_count = fields.Integer(string='# of Invoices', compute='_get_invoiced', readonly=True)
    invoice_ids = fields.One2many("account.invoice", 'rma_id', string='Invoices', readonly=True, copy=False)
    picking_ids = fields.One2many('stock.picking', 'rma_id', string='Picking associated to this RMA')
    delivery_count = fields.Integer(string='Delivery Orders', compute='_compute_picking_ids')
    sale_ids = fields.One2many('sale.order', 'source_rma_id', string='Replacement Sale Orders', readonly=True, copy=False)
    sale_count = fields.Integer(string='# of Sale Orders', compute='_compute_sale_orders', readonly=True)
    purchase_ids = fields.One2many('purchase.order', 'source_rma_id', string='Replacement Purchase Orders', readonly=True, copy=False)
    purchase_count = fields.Integer(string='# of Purchase Orders', compute='_compute_purchase_orders', readonly=True)


    @api.onchange('product_return_type','sale_order_id','purchase_id')
    def order_info(self):
        return_type = self.product_return_type
        destination_domain = DESTINATION_LOCATION_DOMAINS[return_type] if return_type else []
        self.destination_location_id = self.env['stock.location'].search(destination_domain)[0]

        source_domain = SOURCE_LOCATION_DOMAINS[return_type] if return_type else []
        self.source_location_id = self.env['stock.location'].search(source_domain)[0]

        if self.product_return_type == 'incoming' and self.sale_order_id:
            self.partner_id = self.sale_order_id.partner_id
        elif self.product_return_type == 'outgoing' and self.purchase_id:
            self.partner_id = self.purchase_id.partner_id

    @api.multi
    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        rec = super(ProductReturn, self).copy()
        for line in self.return_line_ids:
            vals = line.copy_data(default)[0]
            vals['return_id'] = rec.id
            pred = self.env['product.return.line'].create(vals)
        return rec

    #set soft values bassed off of product return type
    @api.multi
    def write(self, vals):
        if self.product_return_type == 'incoming' and self.company_id.rma_followup_contact and self.company_id.rma_followup_contact.partner_id not in self.message_partner_ids:
            self.message_subscribe(partner_ids=[self.company_id.rma_followup_contact.partner_id.id])
        return super(ProductReturn, self).write(vals)

    @api.model
    def create(self,vals):
        rma = super(ProductReturn, self).create(vals)
        partners = [rma.partner_id.id]
        if rma.product_return_type == 'incoming' and rma.company_id.rma_followup_contact and rma.company_id.rma_followup_contact.partner_id not in rma.message_partner_ids:
            partners.append(rma.company_id.rma_followup_contact.partner_id.id)
        rma.message_subscribe(partner_ids=partners)
        return rma

    @api.multi
    def action_cancel(self):
        self.write({'state': 'cancelled',})
        for picking in self.picking_ids:
            picking.action_cancel()

    @api.multi
    def action_reset(self):
        self.write({'state': 'draft'})
        for pick in self.picking_ids:
            pick.action_cancel()
        self.invoice_ids.action_invoice_cancel()

    @api.multi
    def action_received(self):
        self.write({'state': 'done'})

    @api.model
    def verify_credits(self):
        for rma in self:
            invoice_states = rma.invoice_ids.mapped('state')
            if all(x in ['paid','cancel'] for x in invoice_states):
                rma.action_received()


    #define button for stock moves
    @api.multi
    def action_view_delivery(self):
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        pickings = self.mapped('picking_ids')
        if len(pickings) > 1:
            action['domain'] = [('id', 'in', pickings.ids)]
        elif pickings:
            action['views'] = [(self.env.ref('stock.view_picking_form').id, 'form')]
            action['res_id'] = pickings.id
        return action

    #set rma name based on id, return type, and companyg
    @api.constrains('product_return_type', 'company_id')
    def get_rma_name(self):
        #get prefix based on return type
        company_abbreviation = self.company_id.rma_seq_abbr if self.company_id.rma_seq_abbr else ''
        prefix = 'RMA-'
        if self.product_return_type == 'incoming':
            prefix = 'CRMA-'
        elif self.product_return_type == 'outgoing':
            prefix = 'VRMA-'

        #get sequence based on ID and zerofill
        seq = str(self.id).zfill(4)
        self.name = _('%s%s%s') % (prefix, company_abbreviation, seq)

    #get list of and count for the invoices (Credits/refunds) associated with the picking
    def _get_invoiced(self):
        for rma in self:
            rma.update({'invoice_count': len(rma.invoice_ids.filtered(lambda inv: inv.state != 'cancel')),})

    #define button for viewing the invoices
    @api.multi
    def action_view_invoice(self):
        invoices = self.mapped('invoice_ids')
        action = self.env.ref('account.action_invoice_tree1').read()[0]
        if len(invoices) > 1:
            action['domain'] = [('id', 'in', invoices.ids)]
        elif len(invoices) == 1:
            if self.product_return_type == 'outgoing':
                action['views'] = [(self.env.ref('account.invoice_supplier_form').id, 'form')]
            elif self.product_return_type == 'incoming':
                action['views'] = [(self.env.ref('account.invoice_form').id, 'form')]
            action['res_id'] = invoices.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    #define button for viewing the Replacement Sale Orders
    @api.multi
    def action_view_sales(self):
        sales = self.mapped('sale_ids')
        action = self.env.ref('sale.action_orders').read()[0]
        if len(sales) > 1:
            action['domain'] = [('id', 'in', sales.ids)]
        elif len(sales) == 1:
            action['views'] = [(self.env.ref('sale.view_order_form').id, 'form')]
            action['res_id'] = sales.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    #define button for viewing the Replacement Purchase Orders
    @api.multi
    def action_view_purchases(self):
        pos = self.mapped('purchase_ids')
        action = self.env.ref('purchase.purchase_form_action').read()[0]
        if len(pos) > 1:
            action['domain'] = [('id', 'in', pos.ids)]
        elif len(pos) == 1:
            action['views'] = [(self.env.ref('purchase.purchase_order_form').id, 'form')]
            action['res_id'] = pos.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    #get the picking types
    @api.multi
    def _get_picking_type_id(self):
        warehouse_id = self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)])
        picking_type_id = self.env['stock.picking.type'].search([('code', '=', self.product_return_type), ('warehouse_id', 'in', warehouse_id.ids)], limit=1)
        return picking_type_id and picking_type_id.ids[0]

    #get the picking values
    @api.model
    def _prepare_picking(self):
        return {
            'picking_type_id': self._get_picking_type_id(),
            'partner_id': self.partner_id.id,
            'date': self.order_date,
            'location_id': self.source_location_id.id,
            'location_dest_id': self.destination_location_id.id,
            'reference': self.reference,
            'rma_id': self.id,
        }

    @api.multi
    def _product_qty_by_location(self, product, warehouse_stock_location):

        #update context with source location
        ctx = dict(self._context)
        ctx.update({'location': warehouse_stock_location})

        #get product quantity on hand
        qty = product._product_available()

        qty_wh = 0.0

        if product.id in qty:
            qty_wh = qty[product.id]['qty_available']

        return qty_wh

    @api.multi
    def _create_picking(self):

        #check quantity based on source location
        if self.product_return_type == 'outgoing':
            for line in self.return_line_ids:

                #get quantity on hand based on source location
                qty = self._product_qty_by_location(line.product_id, self.source_location_id.id)
                if qty <= 0.0:
                    raise ValidationError(_("Not enough quantity on hand to return.\nProduct Name = %s\nQuantity On Hand = %s \nReturn Quantity = %s") % (line.product_id.name, qty, line.quantity))

        #check product type
        if any([ptype in ['product', 'consu'] for ptype in self.return_line_ids.mapped('product_id.type')]):

            #prepare picking values
            res = self._prepare_picking()
            if self.product_return_type == 'incoming':
                res.update({'is_return_customer': True,})
            elif self.product_return_type == 'outgoing':
                res.update({'is_return_supplier': True,})

            res.update({
                'origin': self.name,
                'reference': self.reference,
                })

            #create stock picking Delivery order
            picking = self.env['stock.picking'].create(res)
            self.picking_ids |= picking

            #create stock moves
            moves = self.return_line_ids.filtered(lambda r: r.product_id.type in ['product', 'consu']).sudo()._create_stock_moves(picking, self)

        return picking

    @api.multi
    def _get_journal(self):
        journal_pool = self.env['account.journal']
        company_id = self.env.user.company_id.id

        #set journal domain
        journal_domain = [
            ('company_id','=',company_id)
        ]
        if self.product_return_type == 'incoming':
            journal_domain += (('type', '=', 'sale'),)
        elif self.product_return_type == 'outgoing':
            journal_domain += (('type', '=', 'purchase'),)


        #search purchase refund journal
        journal = journal_pool.search(journal_domain, limit=1)

        return journal and journal.id or False

    @api.multi
    def _prepare_invoice_dict(self, partner):
        #get journal
        journal_id = self._get_journal()

        #prepare dict
        inv_dict = {
            'partner_id':partner.id,
            'date_invoice': datetime.today().date(),
            'journal_id': journal_id,
            'user_id': self.env.user.id,
            'rma_id': self.id,
        }

        if self.product_return_type == 'incoming':
            inv_dict.update({
                'account_id': partner.property_account_receivable_id and partner.property_account_receivable_id.id or False,
                'is_return_customer': True,
                'type': 'out_refund',
            })
        elif self.product_return_type == 'outgoing':
            inv_dict.update({
                'account_id': partner.property_account_payable_id and partner.property_account_payable_id.id or False,
                'is_return_supplier': True,
                'type': 'in_refund',
                'reference': self.reference,
            })

        return inv_dict

    @api.multi
    def _create_credit_note(self, credit_items):
        result = []
        AccountInvoiceLine = self.env['account.invoice.line']
        for rma in self:

            #browse partner record
            partner = rma.partner_id

            #prepare invoice dict
            inv_dict = rma._prepare_invoice_dict(partner)
            inv_dict.update({'origin': rma.name})

            #create credit_note
            credit_note = self.env['account.invoice'].create(inv_dict)
            inv_line_list = self.env['account.invoice.line']
            for line in credit_items:

                #set credit note line description
                description = ''
                if line.product_id.default_code:
                    description = '[' + line.product_id.default_code + '] '

                description += line.product_id.name

                #set account
                if rma.product_return_type == 'outgoing':
                    account = line.product_id.property_stock_account_input or line.product_id.categ_id.property_stock_account_input_categ_id
                elif rma.product_return_type == 'incoming':
                    account = AccountInvoiceLine.get_invoice_line_account(credit_note.type, line.product_id, credit_note.fiscal_position_id, credit_note.company_id)

                if not account:
                    raise ValidationError(_("Please update Product stock input account or Product's category stock input account."))

                #set invoice line dict
                inv_line_vals = {
                    'product_id': line.product_id and line.product_id.id or False,
                    'quantity': line.quantity,
                    'name': description,
                    'account_id': account.id,
                    'uom_id': line.uom_id and line.uom_id.id or False,
                    'invoice_id': credit_note.id,
                    'account_analytic_id': line.account_analytic_id and line.account_analytic_id.id or False,
                    'price_unit': line.price_unit,
                }

                new_inv_line = self.env['account.invoice.line'].create(inv_line_vals)
                new_inv_line.return_line_ids |= line
                inv_line_list |= new_inv_line

            # Put the reason in the chatter
            subject = _("Product Return to Credit Note refund")
            body = rma.reason_return
            credit_note.message_post(body=body, subject=subject)

            #call workflow signal and validate Credit Note
            credit_note.action_invoice_open()
            credit_note.write({'state': 'draft'})

        return True

    def _repalcement_order(self, replace_items):
        for rma in self:
            # Shared values
            order_vals = {
                'partner_id': rma.partner_id.id,
                'company_id': rma.company_id.id,
                'state': 'draft',
                'source_rma_id': rma.id,
            }

            # Sale Order Processing
            if rma.product_return_type == 'incoming':
                if rma.sale_order_id:
                    order = rma.sale_order_id
                    order_vals.update({
                        'currency_id': order.currency_id.id,
                        'user_id': order.user_id.id,
                    })

                sale_order = self.env['sale.order'].create(order_vals)
                for line in replace_items:
                    line_vals = line.get_sale_line_vals(sale_order)
                    self.env['sale.order.line'].create(line_vals)

            # Purchase Order Processing
            if rma.product_return_type == 'outgoing':
                if rma.purchase_id:
                    order = rma.purchase_id
                    order_vals.update({
                        'currency_id': order.currency_id.id,
                        'origin': order.name,
                    })
                purchase_order = self.env['purchase.order'].create(order_vals)
                for line in replace_items:
                    line_vals = line.get_po_line_vals(purchase_order)
                    self.env['purchase.order.line'].create(line_vals)


    @api.multi
    def confirm_rma(self):

        for rma in self:
            if not rma.return_line_ids.ids:
                raise ValidationError(_("You can not confirm return without return lines."))
            #restrict User to confirm Return without product tracking lots details
            for line in rma.return_line_ids:
                #check product tracking with lot or serial
                if line.product_id.tracking != 'none':
                    if line.quantity != line.qty_done:
                        raise ValidationError(_("Some products require lots, so you need to specify those first!"))

            #create delivery order
            picking = rma._create_picking()


            if picking:
                #validate picking
                picking.action_confirm()
                picking.action_assign()

            credit_items = rma.return_line_ids.filtered(lambda line: line.return_process == 'credit')
            replace_items = rma.return_line_ids.filtered(lambda line: line.return_process == 'replacement')
            #check condition for creating refund
            if credit_items:
                #create vendor refund bill
                rma._create_credit_note(credit_items)

            if replace_items:
                rma._repalcement_order(replace_items)

            #Move RMA to processing
            rma.write({'state': 'processing'})

        return True


    @api.model
    def action_followup(self):
        for rma in self:
            if rma.state != 'followup':
                rma.write({'state': 'followup',})


    @api.model
    def rma_followup(self):
        settings = self.env['res.config.settings'].get_values()
        followup_date = (datetime.today() - timedelta(days=settings['rma_followup_timeframe'])).replace(hour=23, minute=59, second=59, microsecond=9999)
        rma_follwup_ids = self.env['product.return'].search([
            ('product_return_type', '=', 'incoming'),
            ('state', 'in', ('draft','processing','followup')),
            ('create_date', '<=', followup_date)])
        for rma in rma_follwup_ids:
            rma.action_followup()
            message = rma.name + " requires a followup."
            partner_ids = rma.message_partner_ids.filtered(lambda f: f.name != 'OdooBot').mapped('id')
            rma.sudo().message_post(body=message, message_type='comment', partner_ids=partner_ids)


class ProductReturnLine(models.Model):
    _name = "product.return.line"
    _description = "Product Return Line"

    @api.depends('quantity','price_unit')
    def _compute_amount(self):
        """ Compute the amounts of the Return line. """
        for line in self:
            line.update({'price_total': line.price_unit * line.quantity,})

    return_id = fields.Many2one('product.return', string='Return Product ID')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    qty_available = fields.Float(string="QOH", related="product_id.qty_available")
    op_type = fields.Selection([('serial', 'By Unique Serial Number'), ('lot', 'By Lots'), ('none', 'No Tracking')], default='none', readonly=True, related='product_id.tracking', string='Tracking')
    quantity = fields.Float('Quantity', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', related='product_id.uom_id')
    price_unit = fields.Float('Std Cost', digits=dp.get_precision('Product Price'))
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    company_id = fields.Many2one('res.company', related='return_id.company_id', string='Company', store=True, readonly=True)
    qty_done = fields.Float('Done Qty')
    price_total = fields.Monetary(compute='_compute_amount',string='Sub Total', readonly=True, store=True)
    currency_id = fields.Many2one(related='return_id.currency_id', store=True, string='Currency', readonly=True)
    invoice_lines = fields.Many2many(
        'account.invoice.line',
        'product_return_line_invoice_rel',
        'return_line_id',
        'invoice_line_id',
        string='Invoice Lines', copy=False)
    return_process = fields.Selection([('credit', 'Credit Note'),('replacement','Replacement'),('manual','Manual Processing')], default='manual')

    # Method to limit products to only products on the order
    @api.onchange('product_id')
    def get_product_domain(self):
        product_ids = []
        if self.return_id.product_return_type == 'incoming':
            product_ids =  self.env['product.product'].search([('sale_ok','=',True)]).mapped('id')
            if self.return_id.sale_order_id:
                product_ids = self.env['sale.order.line'].search([('order_id','=',self.return_id.sale_order_id.id)]).mapped('product_id').mapped('id')
        elif self.return_id.product_return_type == 'outgoing':
            product_ids =  self.env['product.product'].search([('purchase_ok','=',True)]).mapped('id')
            if self.return_id.purchase_id:
                product_ids = self.env['purchase.order.line'].search([('order_id','=',self.return_id.purchase_id.id)]).mapped('product_id').mapped('id')
        return {'domain':{'product_id': [('id','in',product_ids)],},}

    @api.onchange('product_id','quantity')
    def _check_price_unit(self):
        for line in self:
            line.price_unit = line.product_id.standard_price
            if line.return_id.product_return_type == 'incoming':
                sale_line = self.env['sale.order.line'].search([('order_id','=',self.return_id.sale_order_id.id),('product_id','=',self.product_id.id)])
                line.price_unit = sale_line.price_unit
            elif line.return_id.product_return_type == 'outgoing':
                po_line = self.env['purchase.order.line'].search([('order_id','=',self.return_id.purchase_id.id),('product_id','=',self.product_id.id)])
                line.price_unit = po_line.price_unit

    @api.onchange('product_id')
    def _onchange_option(self):

        if self.product_id:

            context = self._context

            #restrict to source location
            if not self.return_id.source_location_id:
                self.product_id = False
                warning = {
                    'title': _('Warning!'),
                    'message': _('You must first select a source location!'),
                }
                return {'warning': warning}

            #set UoM and Standard Price
            self.uom_id = self.product_id.uom_po_id and self.product_id.uom_po_id.id
            self.price_unit = self.product_id.standard_price
            if self.return_id.product_return_type == 'incoming':
                self.price_unit = self.return_id.partner_id.property_product_pricelist.get_product_price(self.product_id,1,self.return_id.partner_id)

            #set stock move pool
            moves = self.env['stock.move']

            #last vendor price for product
            #check vendor has last stock move
            vendor_stock_moves_ids = moves.search([('partner_id', '=', self.return_id.partner_id.id), ('state', '=', 'done'), ('product_id', '=', self.product_id.id)])

            if vendor_stock_moves_ids:
                self.price_unit = moves.browse(max(vendor_stock_moves_ids.ids)).price_unit
            else:
                #check last product price in other vendors
                vendor_stock_moves_ids = moves.search([('state', '=', 'done'), ('product_id', '=', self.product_id.id)])
                if vendor_stock_moves_ids:
                    self.price_unit = moves.browse(max(vendor_stock_moves_ids.ids)).price_unit

            #check Unit Price is equal to zero then update with product cost price
            if self.price_unit == 0.0:

                self.price_unit = self.product_id.standard_price

    def get_po_line_vals(self, po):
        return {
            'name': '[%s] %s' % (self.product_id.default_code, self.product_id.name) if self.product_id.default_code else self.product_id.name,
            'order_id': po.id,
            'product_id': self.product_id.id,
            'product_qty': self.quantity,
            'price_unit': self.product_id.price,
            'product_uom': self.product_id.uom_id.id,
            'date_planned': po.date_order,
            'rma_ids': (4,self.id),
        }

    def get_sale_line_vals(self, sale):
        return {
            'name': '[%s] %s' % (self.product_id.default_code, self.product_id.name) if self.product_id.default_code else self.product_id.name,
            'order_id': sale.id,
            'product_id': self.product_id.id,
            'product_uom_qty': self.quantity,
            'price_unit': self.product_id.price,
            'product_uom': self.product_id.uom_id.id,
            'discount': 100.0,
            'rma_ids': (4,self.id),
        }
    @api.multi
    def _create_stock_moves(self, picking, rma):

        #set variables
        moves = self.env['stock.move']
        done = self.env['stock.move'].browse()

        for line in self:
            #prepare stock move values
            template = {
                'name': line.product_id.name or '',
                'product_id': line.product_id.id,
                'product_uom': line.uom_id.id,
                'product_uom_qty': line.quantity,
                'date': line.return_id.order_date,
                'location_id': line.return_id.source_location_id.id,
                'location_dest_id': line.return_id.destination_location_id.id,
                'picking_id': picking.id,
                'partner_id': line.return_id.partner_id.id,
                'state': 'draft',
                'company_id': line.return_id.company_id.id,
                'price_unit': line.price_unit,
                'picking_type_id': line.return_id._get_picking_type_id(),
                'group_id': False,
                'origin': rma.name,
                'return_line_id': line.id,
            }

            done += moves.create(template)

        return done
