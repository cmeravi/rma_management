# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from odoo import api, fields, models, _



class SaleOrder(models.Model):
    _inherit = "sale.order"

    
    def _compute_rma_ids(self):
        for so in self:
            so.rma_count = len(so.rma_ids)

    rma_ids = fields.One2many('product.return','sale_order_id', string='RMA')
    rma_count = fields.Integer(string='RMAs', compute='_compute_rma_ids')

    
    def action_view_rmas(self):
        action = self.env.ref('mdlu_rma_management.action_product_return').read()[0]
        rma_ids = self.mapped('rma_ids')
        if len(rma_ids) > 1:
            action['domain'] = [('id', 'in', rma_ids.ids)]
        elif rma_ids:
            action['views'] = [(self.env.ref('mdlu_rma_management.view_product_return_form').id, 'form')]
            action['res_id'] = rma_ids.id
        return action
