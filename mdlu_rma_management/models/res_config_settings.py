# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from datetime import datetime, timedelta

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    #followup timeframe
    rma_followup_timeframe = fields.Float('Follow Up Timeframe', default=10, help="How long an RMA should be in process before it needs a follow up.")

    rma_followup_contact = fields.Many2one('res.users', string='Customer RMA Followup Contact', domain=[('share', '=', False)], related='company_id.rma_followup_contact', readonly=False,
        help='The person who needs to receive the followup notification.')

    rma_seq_abbr = fields.Char(string='RMA Sequence Abbreviation', related='company_id.rma_seq_abbr', readonly=False)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        res['rma_followup_timeframe'] = float(self.env['ir.config_parameter'].sudo().get_param('product_return.rma_followup_timeframe', default=10.0))
        return res

    @api.model
    def set_values(self):
        self.env['ir.config_parameter'].sudo().set_param('product_return.rma_followup_timeframe', self.rma_followup_timeframe)
        super(ResConfigSettings, self).set_values()
