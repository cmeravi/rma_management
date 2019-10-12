# -*- coding: utf-8 -*-

from odoo import api, fields, models


class Picking(models.Model):
    _inherit = "stock.picking"

    is_return_supplier = fields.Boolean(string="Return to Supplier", default=False)
    is_return_customer = fields.Boolean(string="Return from Customer", default=False)
    reference = fields.Char('RMA Number', readonly=True)
    rma_id = fields.Many2one('product.return', string="RMA #")

    @api.constrains('state')
    def check_rma(self):
        for picking in self:
            if picking.rma_id and picking.rma_id.product_return_type == 'incoming' and picking.state == 'done':
                for move in picking.move_lines:
                    if move.quantity_done != move.return_line_id.quantity:
                        move.return_line_id.quantity = move.quantity_done
                        move.return_line_id.qty_done = move.quantity_done
                picking.rma_id.action_received()



class StockMove(models.Model):
    _inherit = "stock.move"

    return_line_id = fields.Many2one('product.return.line', string='Return Line')
