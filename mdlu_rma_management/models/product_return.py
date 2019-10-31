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

    def _compute_picking_ids(self):
        for rma in self:
            rma.delivery_count = len(rma.picking_ids.filtered(lambda pick: pick.state != 'cancel'))

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
        ('waiting_product', 'Waiting for Product'),
        ('waiting_refund', 'Waiting on Credit'),
        ('followup', 'Followup'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')],
        string='Status', default='draft', track_visibility=True)
    partner_id = fields.Many2one('res.partner', string='Partner', required=True,readonly=True, states={'draft': [('readonly', False)]})
    reference = fields.Char('RMA Number', readonly=True, states={'draft': [('readonly', False)]})
    order_date = fields.Datetime('Order Date', required=True, readonly=True, states={'draft': [('readonly', False)]}, default=fields.Datetime.now)
    is_create_refund = fields.Boolean('Create Credit Note', default=True, readonly=True, states={'draft': [('readonly', False)]})
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
    invoice_ids = fields.One2many("account.move", 'rma_id', string='Invoices', readonly=True, copy=False)
    picking_ids = fields.One2many('stock.picking', 'rma_id', string='Picking associated to this RMA')
    delivery_count = fields.Integer(string='Delivery Orders', compute='_compute_picking_ids')


    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        rec = super(ProductReturn, self).copy()
        for line in self.return_line_ids:
            vals = line.copy_data(default)[0]
            vals['return_id'] = rec.id
            pred = self.env['product.return.line'].create(vals)
        return rec

    #set soft values bassed off of product return type

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


    def action_cancel(self):
        self.write({'state': 'cancelled',})
        for picking in self.picking_ids:
            picking.action_cancel()
        for invoice in self.invoice_ids:
            invoice.button_cancel()

    def action_reset(self):
        self.write({'state': 'draft'})
        for pick in self.picking_ids:
            pick.action_cancel()
        for invoice in self.invoice_ids:
            invoice.button_cancel()


    def action_received(self):
        self.write({'state': 'done'})

    @api.model
    def verify_credits(self):
        for rma in self:
            invoice_states = rma.invoice_ids.mapped('invoice_payment_state')
            if all(x in ['paid','cancel'] for x in invoice_states):
                rma.action_received()


    #define button for stock moves

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
        prefix = 'RMA-'
        if self.product_return_type == 'incoming':
            prefix = 'CRMA-'
        elif self.product_return_type == 'outgoing':
            prefix = 'VRMA-'

        #get sequence based on ID and zerofill
        seq = str(self.id).zfill(4)
        self.name = _('%s%s%s') % (prefix, self.company_id.rma_seq_abbr, seq)

    #get list of and count for the invoices (Credits/refunds) associated with the picking
    def _get_invoiced(self):
        for rma in self:
            rma.update({'invoice_count': len(rma.invoice_ids.filtered(lambda inv: inv.state != 'cancel')),})

    #define button for viewing the invoices
    def action_view_invoice(self):
        invoices = self.mapped('invoice_ids')
        return self.view_invoices(invoices)

    def view_invoices(self,invoices):
        action = self.env.ref('account.action_move_out_refund_type').read()[0]
        if self.product_return_type == 'outgoing':
            action = self.env.ref('account.action_move_in_refund_type').read()[0]
        if len(invoices) > 1:
            action['domain'] = [('id', 'in', invoices.ids)]
        elif len(invoices) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = invoices.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    #get the picking types

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
        return False


    def _get_journal(self):
        #set journal domain
        journal_domain = [
            ('company_id','=',self.env.user.company_id.id)
        ]
        if self.product_return_type == 'incoming':
            journal_domain += (('type', '=', 'sale'),)
        elif self.product_return_type == 'outgoing':
            journal_domain += (('type', '=', 'purchase'),)


        #search purchase refund journal
        journal = self.env['account.journal'].search(journal_domain, limit=1)

        return journal and journal.id or False


    def _prepare_invoice_dict(self, partner):
        #get journal
        journal_id = self._get_journal()

        #prepare dict
        inv_dict = {
            'invoice_payment_state': 'not_paid',
            'partner_id':partner.id,
            'invoice_date': datetime.today().date(),
            'journal_id': journal_id,
            'user_id': self.env.user.id,
            'rma_id': self.id,
            'invoice_line_ids': [],
        }

        if self.product_return_type == 'incoming':
            inv_dict.update({
                'is_return_customer': True,
                'type': 'out_refund',
            })
        elif self.product_return_type == 'outgoing':
            inv_dict.update({
                'is_return_supplier': True,
                'type': 'in_refund',
                'ref': self.reference,
            })

        return inv_dict


    def _create_credit_note(self):
        result = []
        for rma in self:

            #browse partner record
            partner = rma.partner_id

            #prepare invoice dict
            inv_dict = rma._prepare_invoice_dict(partner)
            inv_dict.update({'invoice_origin': rma.name})

            for line in rma.return_line_ids:

                #set credit note line description
                description = ''
                if line.product_id.default_code:
                    description = '[' + line.product_id.default_code + '] '

                description += line.product_id.name

                #set account
                account_type = 'income' if rma.product_return_type == 'outgoing' else 'expense'
                account = line.product_id.product_tmpl_id._get_product_accounts()[account_type]

                if not account:
                    raise ValidationError(_("Please update Product stock input account or Product's category stock input account."))
                #set invoice line dict
                inv_line_vals = {
                    'name': description,
                    'analytic_account_id': line.account_analytic_id.id,
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                    'product_uom_id': line.uom_id.id,
                    'account_id': account.id,
                    'price_unit': line.price_unit if rma.product_return_type == 'incoming' else line.last_price_unit,
                }

                inv_dict['invoice_line_ids'].append((0,0,inv_line_vals))

            credit_note = self.env['account.move'].create(inv_dict)

            # Put the reason in the chatter
            subject = _("Product Return to Credit Note refund")
            body = rma.reason_return
            credit_note.message_post(body=body, subject=subject)

            #call workflow signal and validate Credit Note
            credit_note.action_post()
            credit_note.write({'state': 'draft'})

        return True



    def create_delivery_order(self):

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

            #check condition for creating refund
            if rma.is_create_refund:
                #create vendor refund bill
                rma._create_credit_note()

            #set state equal to done
            if rma.product_return_type == 'incoming':
                rma.write({'state': 'waiting_product'})
            if rma.product_return_type == 'outgoing':
                rma.write({'state': 'waiting_refund'})

            if all(x not in ['product', 'consu'] for x in rma.return_line_ids.mapped('product_id').mapped('type')):
                rma.action_received()

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
            ('state', 'in', ('draft','waiting_product','followup')),
            ('create_date', '<=', followup_date)])
        for rma in rma_follwup_ids:
            rma.action_followup()
            message = rma.name + " requires a followup."
            partner_ids = rma.message_partner_ids.filtered(lambda f: f.name != 'OdooBot').mapped('id')
            rma.sudo().message_post(body=message, message_type='comment', partner_ids=partner_ids)


class ProductReturnLine(models.Model):
    _name = "product.return.line"
    _description = "Product Return Line"

    @api.depends('quantity','price_unit','last_price_unit')
    def _compute_amount(self):
        """ Compute the amounts of the Return line. """
        for line in self:
            price = line.price_unit if line.return_id.product_return_type == 'incoming' else line.last_price_unit
            line.update({'price_total': price * line.quantity,})



    return_id = fields.Many2one('product.return', string='Return Product ID')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    qty_available = fields.Float(string="QOH", related="product_id.qty_available")
    op_type = fields.Selection([('serial', 'By Unique Serial Number'), ('lot', 'By Lots'), ('none', 'No Tracking')], default='none', readonly=True, related='product_id.tracking', string='Tracking')
    quantity = fields.Float('Quantity', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', related='product_id.uom_id')
    price_unit = fields.Float('Std Cost', digits=dp.get_precision('Product Price'))
    last_price_unit = fields.Float('Unit Price', digits=dp.get_precision('Product Price'))
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    company_id = fields.Many2one('res.company', related='return_id.company_id', string='Company', store=True, readonly=True)
    qty_done = fields.Float('Done Qty')
    price_total = fields.Monetary(compute='_compute_amount',string='Sub Total', readonly=True, store=True)
    currency_id = fields.Many2one(related='return_id.currency_id', store=True, string='Currency', readonly=True)
    invoice_lines = fields.Many2many(
        'account.move.line',
        'product_return_line_invoice_rel',
        'return_line_id',
        'invoice_line_id',
        string='Invoice Lines', copy=False)

    @api.constrains('product_id','quantity')
    def _check_price_unit(self):
        for line in self:
            line.price_unit = line.product_id.standard_price
            if line.return_id.product_return_type == 'incoming':
                line.price_unit = line.return_id.partner_id.property_product_pricelist.get_product_price(line.product_id,1,line.return_id.partner_id)

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
                self.last_price_unit = moves.browse(max(vendor_stock_moves_ids.ids)).price_unit
            else:
                #check last product price in other vendors
                vendor_stock_moves_ids = moves.search([('state', '=', 'done'), ('product_id', '=', self.product_id.id)])
                if vendor_stock_moves_ids:
                    self.last_price_unit = moves.browse(max(vendor_stock_moves_ids.ids)).price_unit

            #check Unit Price is equal to zero then update with product cost price
            if self.last_price_unit == 0.0:

                self.last_price_unit = self.product_id.standard_price


    def _create_stock_moves(self, picking, rma):

        #set variables
        moves = self.env['stock.move']
        done = self.env['stock.move'].browse()

        for line in self:
            price = line.price_unit if line.return_id.product_return_type == 'incoming' else line.last_price_unit
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
                'price_unit': price,
                'picking_type_id': line.return_id._get_picking_type_id(),
                'group_id': False,
                'origin': rma.name,
                'return_line_id': line.id,
            }

            done += moves.create(template)

        return done
