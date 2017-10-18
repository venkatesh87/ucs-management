/*
 * Copyright 2011-2017 Univention GmbH
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
/*global define */

define([
	"dojo/_base/declare",
	"dojo/_base/array",
	"dijit/TitlePane",
	"dijit/_Container",
	"dojox/grid/_Grid",
	"umc/tools"
], function(declare, array, TitlePane, _Container, _Grid, tools) {
	return declare("umc.widgets.TitlePane", [ TitlePane, _Container ], {
		// summary:
		//		Widget that extends dijit.TitlePane with methods of a container widget.

		startup: function() {
			this.inherited(arguments);

			array.forEach(this.getChildren(), function(ichild) {
				if (ichild.startup && !ichild._started) {
					ichild.startup();
				}
			});


			// FIXME: Workaround for refreshing problems with datagrids when they are rendered
			//        in a closed TitlePane

			// iterate over all tabs
			array.forEach(this.getChildren(), function(iwidget) {
				if (iwidget.isInstanceOf(_Grid)) {
					// hook to changes for 'open'
					this.own(this.watch('open', function(attr, oldVal, newVal) {
						if (newVal) {
							// recall startup when the TitelPane gets shown
							iwidget.startup();
						}
					}));
				}
			}, this);
		}
	});
});

