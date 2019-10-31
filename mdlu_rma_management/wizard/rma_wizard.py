# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

RETURN_TYPES = {
    'sale.order': 'incoming',
    'purchase.order': 'outgoing',
}

LINE_MODELS = {
    'sale.order': 'sale.order.line',
    'purchase.order': 'purchase.order.line',
}

SOURCE_LOCATION_DOMAINS = {
    'incoming': [('active', '=', True), ('usage', '=', 'customer')],
    'outgoing': [('active', '=', True), ('usage', '=', 'internal')],
}

DESTINATION_LOCATION_DOMAINS = {
    'incoming': [('active', '=', True), ('usage', '=', 'internal')],
    'outgoing': [('active', '=', True), ('usage', '=', 'supplier')],
}

class RMAWizard(models.TransientModel):
    _name = 'rma.wizard'
    _description = 'RMA Wizard'

    @api.model
    def get_order_id(self):
        return self._context.get('active_id')

    @api.model
    def get_active_model(self):
        return self._context.get('active_model')

    #Set domains based on model
    @api.onchange('source_location_id')
    def set_source_domain(self):
        location_ids = []
        return_type = RETURN_TYPES[self._context.get('active_model')]
        location_ids = self.env['stock.location'].search(SOURCE_LOCATION_DOMAINS[return_type]).mapped('id')
        return{'domain':{'source_location_id': [('id','in',location_ids)],},}

    @api.onchange('destination_location_id')
    def set_destination_domain(self):
        location_ids = []
        return_type = RETURN_TYPES[self._context.get('active_model')]
        location_ids = self.env['stock.location'].search(DESTINATION_LOCATION_DOMAINS[return_type]).mapped('id')
        return{'domain':{'destination_location_id': [('id','in',location_ids)],},}

    order_id = fields.Integer(string='Order', default=get_order_id)
    order_model = fields.Char(string='Active Model', default=get_active_model)

    rma_line_ids = fields.One2many('rma.wizard.line', 'rma_wizard_id', string='Wizard Lines')
    reason_return = fields.Text('Reason for Return')
    source_location_id = fields.Many2one('stock.location', string='Source Location', required=True)
    destination_location_id = fields.Many2one('stock.location', string='Destination Location', required=True)

    
    def get_data(self):
        self.ensure_one()
        context = dict(self._context or {})
        active_id = context.get('active_id',self.order_id)
        model = context.get('active_model',self.order_model)
        order_id = self.env[model].browse(active_id)

        vals = {
            'product_return_type': RETURN_TYPES[model],
            'source_location_id': self.source_location_id.id,
            'destination_location_id': self.destination_location_id.id,
            'partner_id': order_id.partner_id.id,
            'reason_return': self.reason_return,
            'company_id': order_id.company_id.id,
        }

        if 'sale.order' == model:
            vals['sale_order_id'] = order_id.id
        elif 'purchase.order' == model:
            vals['purchase_id'] = order_id.id

        rma_id = self.env['product.return'].create(vals)

        for order_line in self.rma_line_ids:
            line_vals = {
                'return_id': rma_id.id,
                'product_id': order_line.product_id.id,
                'quantity': order_line.quantity,
            }
            rma_line = self.env['product.return.line'].create(line_vals)

        action = self.env.ref('mdlu_rma_management.action_product_return').read()[0]
        action['views'] = [(self.env.ref('mdlu_rma_management.view_product_return_form').id, 'form')]
        action['res_id'] = rma_id.id
        return action



class RMAWizardLine(models.TransientModel):
    _name = 'rma.wizard.line'
    _description = 'RMA Wizard Line'

    @api.onchange('product_id')
    def default_quantity(self):
        model = self.rma_wizard_id.order_model
        order_id = self.rma_wizard_id.order_id
        line_id = self.env[LINE_MODELS[model]].search([('order_id','=',order_id),('product_id','=',self.product_id.id)])
        self.quantity = line_id.product_uom_qty


    # Method to limit products to only products on the order
    @api.onchange('product_id')
    def get_product_domain(self):
        product_ids = self.env[LINE_MODELS[self.rma_wizard_id.order_model]].search([('order_id','=',self.rma_wizard_id.order_id)]).mapped('product_id').mapped('id')
        return {'domain':{'product_id': [('id','in',product_ids)],},}

    rma_wizard_id = fields.Many2one('rma.wizard', string='Wizard Order')
    product_id = fields.Many2one('product.product', string='Product')
    quantity = fields.Float('Quantity Returned')
