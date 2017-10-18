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
/*global define console*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"umc/widgets/Button"
], function(declare, lang, Button) {
	return declare("umc.widgets.SubmitButton", Button, {
		type: 'submit',

		// defaultButton: Boolean
		//		The submit button will always be rendered as the default button
		defaultButton: true,

		uninitialize: function() {
			// Sometimes after a form is destroyed, there would be tracebacks as a submit
			// event handler would try to access this.node (see dijit/form/_ButtonMixin:_onClick).
			// Therefore, set type to 'button' to avoid these problems
			this.type = 'button';

			this.inherited(arguments);
		}
	});
});
