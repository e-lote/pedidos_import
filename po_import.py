# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp.osv import fields, osv
from openerp.tools.translate import _
from datetime import date
from openerp import netsvc
from StringIO import StringIO
import csv
import base64


class purchase_order_import(osv.osv_memory):
    _name = 'po.import'
    _description = 'Importa pedidos'

    def _default_lote(self, cr, uid, ids, context=None):
        lote_obj = self.pool.get('elote.lote')
        lote_open_ids = lote_obj.search(cr, uid, [('state','=','open')])
        return lote_open_ids and lote_open_ids[0] or False

    _columns = {
        'filename_purchase_order': fields.binary(string='PO Filename', required=True),
        'lote_id': fields.many2one('elote.lote', string='Lote', domain="[('state','=','open')]", required=True),
        'first_row_column': fields.boolean('1st Row Column Names'),
    }

    _defaults = {
        'lote_id': _default_lote,
        'first_row_column': True,
        }

    def po_import(self, cr, uid, ids, context=None):
        partner_obj = self.pool.get('res.partner')
        user_obj = self.pool.get('res.users')
        product_obj = self.pool.get('product.product')
        supplierinfo_obj = self.pool.get('product.supplierinfo')
        po_obj = self.pool.get('purchase.order')

        for wiz in self.browse(cr, uid, ids):
            ss = StringIO(base64.b64decode(wiz.filename_purchase_order))
            ireader = csv.reader(ss)

            # Ignore first line
            if wiz.first_row_column:
                s = ireader.next()
                if len(s) != 4:
                    raise osv.except_osv(_('Error!'), _("File must have 4 columns: Supplier,Delver to,ISBN, Quantity"))

            # Storage for each purchase order for each partner
            vals = {}

            # Read all lines
            for row in ireader:
                # Check column count
                if len(row) != 4:
                    raise osv.except_osv(_('Error!'), _("Line %s: File must have 4 columns: Supplier,Delver to,ISBN, Quantity.") % ireader.line_num)

                # Translate values
                supplier_name, delivery_to, isbn, quantity = row
                partner_id = (partner_obj.search(cr, uid, ['|',('name','=',supplier_name),('ref','=',supplier_name)])+
                              [False])[0]
                product_id = (product_obj.search(cr, uid, [('ean13','=',isbn)], context={'search_default_elote_id': wiz.lote_id.id,
                                                                                         'search_default_partner_id': partner_id})+
                              [False])[0]
                user_id = (user_obj.search(cr, uid, [('id','in',[u.id for u in wiz.lote_id.user_ids]), '|',
                                                     '|',('partner_id.name','=',delivery_to),('partner_id.ref','=',delivery_to),
                                                     '|',('partner_id.parent_id.name','=',delivery_to),('partner_id.parent_id.ref','=',delivery_to)])+
                              [False])[0] if uid == 1 else uid
                quantity = int(quantity) if unicode(quantity).isnumeric() and int(quantity) > 0 else False

                # Check values
                if not(partner_id and user_id and product_id and quantity):
                    raise osv.except_osv(_('Error!'), _("Line %s: Input (%s,%s,%s,%s) has interpreted as (%s,%s,%s,%s).") %
                                         (ireader.line_num, supplier_name, delivery_to, isbn, quantity,
                                          partner_id or 'Not found', user_id or 'Not found', product_id or 'Not found', quantity or 'Not positive integer, or cero'))

                supplierinfo_id = (supplierinfo_obj.search(cr, uid, [('lote_id','=',wiz.lote_id.id),
                                                                     ('name','=',partner_id),
                                                                     ('product_tmpl_id.product_variant_ids','in',product_id)])
                                   +[False])[0]
                if not supplierinfo_id:
                    raise osv.except_osv(_('Error!'), _("Line %s: No price information about %s (%s) for the supplier '%s' in lote '%s'.") %
                                         (ireader.line_num,
                                          isbn,
                                          product_obj.browse(cr, uid, product_id).name,
                                          partner_obj.browse(cr, uid, partner_id).name,
                                          wiz.lote_id.name))
                supplierinfo = supplierinfo_obj.browse(cr, uid, supplierinfo_id)

                # Create purchase order line
                line_vals = {
                    'product_id': product_id,
                    'name': product_obj.browse(cr, uid, product_id).name,
                    'date_planned': str(date.today()),
                    'boxes': quantity,
                    'price_unit': supplierinfo.supplier_price,
                    'product_qty': supplierinfo.carton_quantity * quantity,
                }

                # Build values for purchase order for each partner.
                if partner_id in vals:
                    # Exists purchase order, add product.
                    vals[partner_id]['order_line'].append((0,0,line_vals))
                else:
                    # Not exists purchase order, create one.
                    vals[partner_id] = {
                        'partner_id': partner_id,
                        'responsible_id': user_id,
                        'invoice_method': 'manual',
                        'date_order': str(date.today()),
                        'pricelist_id': 1,
                        'location_id': 1,
                        'order_line': [(0,0,line_vals)]
                    }

            # Create PO in database.
            po_ids =  [ po_obj.create(cr, uid, po) for po in vals.values() ]

            return {
                'name': _('Purchase order'),
                'domain': [('id', 'in', po_ids)],
                'res_model': 'purchase.order',
                'type': 'ir.actions.act_window',
                'view_id': False,
                'view_mode': 'tree,form',
                'view_type': 'form',
                'limit': 80,
            }

purchase_order_import()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
