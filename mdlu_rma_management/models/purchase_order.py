# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, SUPERUSER_ID, _


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    
    def _compute_rma_ids(self):
        for po in self:
            po.rma_count = len(po.rma_ids)

    rma_ids = fields.One2many('product.return', 'purchase_id', string='RMA')
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
