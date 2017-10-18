/*
 * Copyright 2014-2017 Univention GmbH
 *
 * http://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <http://www.gnu.org/licenses/>.
 */
/*global define*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/aspect",
	"dijit/registry"
], function(declare, lang, aspect, registry) {
	return declare("umc.widget._RegisterOnShowMixin", [], {
		_registerAtParentOnShowEvents: function(callback) {
			// iterate up the DOM and register the given callback
			// at each ancestor widget that has a _onShow() method
			var node = this.domNode;
			while (node) {
				var widget = registry.getEnclosingWidget(node.parentNode);
				if (!widget) {
					node = null;
					continue;
				}
				if (widget._onShow) {
					this.own(aspect.after(widget, '_onShow', callback));
				}
				node = widget.domNode;
			}
		}
	});
});
