# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.tools import float_is_zero, float_compare

class AccountMove(models.Model):
    _inherit = "account.move"

    rma_id = fields.Many2one('product.return', string='RMA')
    is_return_supplier = fields.Boolean(string="Return to Supplier",
                                        default=False)
    is_return_customer = fields.Boolean(string="Return from Customer",
                                        default=False)

    @api.constrains('invoice_payment_state')
    def check_rma(self):
        for invoice in self:
            if invoice.invoice_payment_state == 'paid' and invoice.rma_id and invoice.rma_id.product_return_type == 'outgoing':
                invoice.rma_id.verify_credits()

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    return_line_ids = fields.Many2many(
        'product.return.line',
        'product_return_line_invoice_rel',
        'invoice_line_id',
        'return_line_id',
        string='RMA Lines', readonly=True, copy=False)
