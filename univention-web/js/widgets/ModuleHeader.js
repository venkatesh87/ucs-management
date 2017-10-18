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
/*global define document*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/Deferred",
	"dojo/on",
	"dojo/dom-class",
	"dojo/dom-geometry",
	"dojo/dom-style",
	"dojo/_base/window",
	"umc/tools",
	"umc/dialog",
	"umc/store",
	"umc/widgets/ContainerWidget",
	"umc/widgets/Text",
	"umc/widgets/Button",
	"dojo/topic",
	"put-selector/put",
	"umc/i18n!"
], function(declare, lang, array, Deferred, on, domClass, geometry, domStyle, baseWin, tools, dialog, store, ContainerWidget, Text, Button, topic, put,  _) {

	return declare('umc.widgets.ModuleHeader', [ContainerWidget], {

		baseClass: 'umcModuleHeader',
		isModuleTabSelected: false,
		_title: null,
//		buttons: null,
		_outerContainer: null,

		_setTitleAttr: function(title) {
			this._title.set('content', title);
		},

		buildRendering: function() {
			this.inherited(arguments);

			this._left = new ContainerWidget({
				baseClass: 'umcModuleHeaderLeft'
			});
			this._right = new ContainerWidget({
				baseClass: 'umcModuleHeaderRight'
			});
			this._outerContainer = new ContainerWidget({
				baseClass: 'umcModuleHeaderOuterContainer'
			});
			var container = new ContainerWidget({
				baseClass: 'umcModuleHeaderWrapper container'
			});
			this.addChild(this._outerContainer);
			this._outerContainer.addChild(container);
			container.addChild(this._left);
			container.addChild(this._right);

			this._title = new Text({
				content: this.get('title'),
				baseClass: 'umcModuleTitle'
			});
			this._left.addChild(this._title);

//			array.forEach(this.buttons.$order$, lang.hitch(this, function(button) {
//				this._right.addChild(button);
//			}));
		}
	});
});
