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
/*global define*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"umc/dialog",
	"umc/tools",
	"umc/widgets/Module",
	"umc/widgets/Page",
	"umc/widgets/Grid",
	"umc/widgets/SearchForm",
	"umc/widgets/SearchBox",
	"umc/i18n!umc/modules/services"
], function(declare, lang, array, dialog, tools, Module, Page, Grid, SearchForm, SearchBox, _) {
	return declare("umc.modules.services", [ Module ], {

		moduleStore: null,
		_grid: null,
		_page: null,
		_searchWidget: null,

		idProperty: 'service',

		buildRendering: function() {
			this.inherited(arguments);

			this._page = new Page({
				helpText: _('This module shows the system services and their current status. Specified services can be configured, started and stopped.'),
				fullWidth: true
			});
			this.addChild(this._page);

			var actions = [{
				name: 'start',
				label: _('Start'),
				iconClass: 'umcPlayIcon',
				callback: lang.hitch(this, function(data) {
					if (data.length) {
						var command = 'services/start';
						var confirmMessage = _('Please confirm to start the following services: ');
						var errorMessage = _('Starting the following services failed: ');
						this._changeState(data, command, confirmMessage, errorMessage);
					}
				}),
				isStandardAction: true,
				isMultiAction: true
			}, {
				name: 'stop',
				label: _('Stop'),
				iconClass: 'umcStopIcon',
				callback: lang.hitch(this, function(data) {
					if (data.length) {
						var command = 'services/stop';
						var confirmMessage = _('Please confirm to stop the following services: ');
						var errorMessage = _('Stopping the following services failed: ');
						this._changeState(data, command, confirmMessage, errorMessage);
					}
				}),
				isStandardAction: true,
				isMultiAction: true
			}, {
				name: 'restart',
				label: _('Restart'),
				iconClass: 'umcRefreshIcon',
				callback: lang.hitch(this, function(data) {
					if (data.length) {
						var command = 'services/restart';
						var confirmMessage = _('Please confirm to restart the following services: ');
						var errorMessage = _('Restarting the following services failed: ');
						this._changeState(data, command, confirmMessage, errorMessage);
					}
				}),
				isStandardAction: true,
				isMultiAction: true
			}, {
				name: 'startAutomatically',
				label: _('Start automatically'),
				callback: lang.hitch(this, function(data) {
					var command = 'services/start_auto';
					var confirmMessage = _('Please confirm to automatically start the following services: ');
					var errorMessage = _('Could not change start type of the following services: ');
					this._changeState(data, command, confirmMessage, errorMessage);
				}),
				isStandardAction: false,
				isMultiAction: true
			}, {
				name: 'startManually',
				label: _('Start manually'),
				callback: lang.hitch(this, function(data) {
					var command = 'services/start_manual';
					var confirmMessage = _('Please confirm to manually start the following services: ');
					var errorMessage = _('Could not change start type of the following services: ');
					this._changeState(data, command, confirmMessage, errorMessage);
				}),
				isStandardAction: false,
				isMultiAction: true
			}, {
				name: 'startNever',
				label: _('Start never'),
				callback: lang.hitch(this, function(data) {
					var command = 'services/start_never';
					var confirmMessage = _('Please confirm to never start the following services: ');
					var errorMessage = _('Could not change start type of the following services: ');
					this._changeState(data, command, confirmMessage, errorMessage);
				}),
				isStandardAction: false,
				isMultiAction: true
			}];

			var columns = [{
				name: 'service',
				label: _('Name')//,
			}, {
				name: 'isRunning',
				label: _('Status'),
//				width: 'adjust',  // FIXME: the label must be longer than entries
				width: '15%',
				formatter: lang.hitch(this, function(value) {
					if (value === true) {
						return _('running');
					} else {
						return _('stopped');
					}
				})
			}, {
				name: 'autostart',
				label: _('Start type'),
//				width: 'adjust',  // FIXME: the label must be longer than entries
				width: '15%',
				formatter: lang.hitch(this, function(value) {
					if (value == 'no') {
						return _('Never');
					} else if (value == 'manually') {
						return _('Manually');
					} else {
						return _('Automatically');
					}
				})
			}, {
				name: 'description',
				label: _('Description'),
				formatter: lang.hitch(this, function(value) {
					if (value === null) {
						return '-';
					} else {
						return value;
					}
				})
			}];

			this._grid = new Grid({
				region: 'main',
				actions: actions,
				columns: columns,
				moduleStore: this.moduleStore,
				query: {
					pattern: ''
				}
			});

			var widgets = [{
				type: SearchBox,
				name: 'pattern',
				value: '',
				inlineLabel: _('Search...'),
				onSearch: lang.hitch(this, function() {
					this._searchWidget.submit();
				})
			}];

			this._searchWidget = new SearchForm({
				region: 'nav',
				hideSubmitButton: true,
				widgets: widgets,
				layout: ['pattern'],
				onSearch: lang.hitch(this._grid, 'filter')
			});

			this._page.addChild(this._searchWidget);
			this._page.addChild(this._grid);

			this._page.startup();
    	},

		reloadGrid: function() {
			data = this._searchWidget.get('value');
			this._grid.filter(data);
		},

		_changeState: function(data, command, confirmMessage, errorMessage) {
			confirmMessage += '<ul>';
			array.forEach(data, function(idata) {
				confirmMessage += '<li>' + idata + '</li>';
			});
			confirmMessage += '</ul>';

			dialog.confirm(confirmMessage, [{
				label: _('OK'),
				callback: lang.hitch(this, function() {
					this.standbyDuring(tools.umcpCommand(command, data)).then(lang.hitch(this, function(response) {
						if (response.result.success === false) {
							errorMessage += '<ul>';
							array.forEach(response.result.objects, function(item) {
								errorMessage += '<li>' + item + '</li>';
							});
							errorMessage += '</ul>';
							dialog.alert(errorMessage);
						}
						this.reloadGrid();
					}));
				})
			}, {
				'default': true,
				label: _('Cancel')
			}]);
		}
	});
});
