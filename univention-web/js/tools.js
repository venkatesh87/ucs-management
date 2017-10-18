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
/*global define,require,console,setTimeout,window,document*/

define([
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/_base/window",
	"dojo/request/xhr",
	"dojo/_base/xhr",
	"dojo/Deferred",
	"dojo/promise/all",
	"dojo/json",
	"dojo/string",
	"dojo/topic",
	"dojo/cookie",
	"dijit/Dialog",
	"dijit/TitlePane",
	"dojox/timing/_base",
	"dojox/html/styles",
	"dojox/html/entities",
	"umc/widgets/ContainerWidget",
	"umc/widgets/ConfirmDialog",
	"umc/widgets/Text",
	"umc/i18n/tools",
	"umc/i18n!"
], function(lang, array, _window, xhr, basexhr, Deferred, all, json, string, topic, cookie, Dialog, TitlePane, timing, styles, entities, ContainerWidget, ConfirmDialog, Text, i18nTools, _) {
	// in order to break circular dependencies (umc.tools needs a Widget and
	// the Widget needs umc/tools), we define umc/dialog as an empty object and
	// require it explicitely
	var tools = {};
	var login = {}, TextBox = {}, TextArea = {};
	var dialog = {
		login: function() {
			return new Deferred();
		},
		notify: function() {},
		alert: function() {},
		centerAlertDialog: function() {}
	};

	tools.loadLicenseDataDeferred = new Deferred();

	require(['umc/dialog', 'login', 'umc/widgets/TextBox', 'umc/widgets/TextArea'], function(_dialog, _login, _TextBox, _TextArea) {
		// register the real umc/dialog module in the local scope
		dialog = _dialog;
		login = _login;
		TextArea = _TextArea;
		TextBox = _TextBox;

		// automatically read in license information and re-read meta data upon first login
		login.onInitialLogin(function() {
			// after login, the meta data contains additional information
			tools.loadMetaData().then(function() {
				tools.loadLicenseDataDeferred.resolve();
			});
		});
	});

	// define umc/tools
	lang.mixin(tools, {
		_status: {
			username: null,
			hostname: '',
			domainname: '',
			overview: true,
			setupGui: false,
			loggingIn: false,
			loggedIn: false,
			feedbackSubject: '[UMC-Feedback] Traceback',
			feedbackAddress: 'feedback@univention.de',
			// default value for the session timeout
			// it will be replaced by the ucr variable 'umc/http/session/timeout' onLogin
			sessionTimeout: 300,
			sessionLastRequest: new Date(0),
			autoStartModule: null,
			autoStartFlavor: null,
			numOfTabs: 0
		},

		loadMetaData: function() {
			// loading the meta data is done by default via config.js...
			// calling this function is only necessary for reloading data,
			// e.g., if you know that it must have changed
			var deferred = new Deferred();

			// use a time stamp as query string to make sure that we reload the file
			var timestamp = (new Date()).getTime();
			require(['umc/json!/univention/get/meta?' + timestamp], lang.hitch(this, function(meta) {
				lang.mixin(this._status, meta.result);
				deferred.resolve(tools.status());
			}));
			return deferred.promise;
		},

		status: function(/*String?*/ key, /*Mixed?*/ value) {
			// summary:
			//		Sets/gets status information. With no parameters given,
			//		returns a dict with status information (username, domainname,
			//		hostname, isSetUpGUI, ...).
			//		With one parameter given, returns the value of the specified key.
			//		With two parameters, sets the value of the specified key.
			//		Also contains the properties given
			//		to `umc/app::start()`. The following properties exist:
			//		* username (String): The username of the authenticated user.
			//		* hostname (String): The hostname on which the UMC is running.
			//		* domainname (String): The domainname on which the UMC is running.
			//		* overview (Boolean): Specifies whether or not the overview is visible and the header is displayed or not.
			// key: String?
			//		If given, only the value for the specified property is returned.

			if (undefined === key) {
				// return the whole dictionary
				return this._status;
			}
			if (typeof key === "string") {
				if (undefined === value) {
					// return the specified key
					return this._status[key];
				}
				// set the value
				this._status[key] = value;
			}
			return undefined;
		},

		_regUUID: /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
		_fakeUUID: '00000000-0000-0000-0000-000000000000',
		isUUID: function(uuid) {
			return this._regUUID.test(uuid) && uuid != this._fakeUUID;
		},

		getCookies: function() {
			return {
				sessionID: cookie('UMCSessionId-' + document.location.port) || cookie('UMCSessionId'),
				username: cookie('UMCUsername-' + document.location.port) || cookie('UMCUsername')
			};
		},

		setSessionCookie: function(value, params) {
			var key = 'UMCSessionId' + (document.location.port ? '-' + document.location.port : '');
			cookie(key, value, params);
		},

		setUsernameCookie: function(value, params) {
			var key = 'UMCUsername' + (document.location.port ? '-' + document.location.port : '');
			cookie(key, value, params);
		},

		closeSession: function() {
			// summary:
			//		Reset the session cookie in order to close the session from the client side.
			this.status('sessionLastRequest', new Date(0));
			this.setSessionCookie(null, {
				expires: -1,
				path: '/univention/'
			});
		},

		renewSession: function() {
			topic.publish('/umc/actions', 'session', 'renew');
			this.resetModules();
			return tools.umcpCommand('get/newsession', {}, false).then(null, lang.hitch(this, function(err) {
				console.error('WARNING: Could not renew session... forcing re-login again instead:', err);
				this.closeSession();
				tools.checkReloadRequired();
				return login.showLoginDialog();
			}));
		},

		holdSession: function() {
			// summary:
			//		Set the expiration time of the current session to 24 hours.
			var date = new Date((new Date()).getTime() + 1000 * 60 * 60 * 24);
			this.status('sessionLastRequest', date);
		},

		_updateSession: function() {
			// summary:
			//		Reset timestamp of last received request
			this.status('sessionLastRequest', new Date());
		},

		_checkSessionTimer: null,
		_checkSessionRequest: null,

		checkSession: function(enable) {
			// summary:
			//		Create a background process that checks each second the validity of the session
			//		cookie. As soon as the session is invalid, the login screen will be shown.
			if (enable === false) {
				// stop session checking
				if (this._checkSessionTimer && this._checkSessionTimer.isRunning) {
					this._checkSessionTimer.stop();
				}
				return;
			}

			if (this._checkSessionRequest) {
				return;
			}

			if (!this._checkSessionTimer) {
				// create a new timer instance
				this._checkSessionTimer = new timing.Timer(30000);
				this._checkSessionTimer.onTick = lang.hitch(this, function() {
					// check whether session is still valid
					this._checkSessionRequest = login.sessioninfo().otherwise(lang.hitch(this, function(error) {
						error = tools.parseError(error);
						if (error.status !== 401) {
							// ignore any other error than unauthenticated (e.g. not reachable)
							return;
						}
						if (tools.status('loggingIn')) {
							// login dialog is already running
							return;
						}
						login.sessionTimeout(error);
					}));
					this._checkSessionRequest.always(lang.hitch(this, function() {
						this._checkSessionRequest = null;
					}));
				});
			}

			// start session checking
			if (!this._checkSessionTimer.isRunning) {
				this._checkSessionTimer.start();
			}
		},

		_reloadDialog: null,
		_reloadDialogOpened: false,
		askToReload: function() {
			if (this.status('ignorePageReload')) {
				return;
			}
			if (!this._reloadDialog) {
				// The URL does not exists, so the symlink is deleted
				this._reloadDialog = new ConfirmDialog({
					title: _("UMC reload required"),
					message: _("A reload of the Univention Management Console is required to use new modules.<br>Currently opened modules may not work properly.<br>Do you want to reload the page?"),
					options: [{
						label: _('Cancel'),
						callback: lang.hitch(this, function() {
							this._reloadDialog.hide();
						}),
						'default': true
					}, {
						label: _('Reload'),
						callback: function() {
							window.location.reload(true);
						}
					}]
				});
			}
			if (!this._reloadDialog.open && !this._reloadDialogOpened) {
				this._reloadDialog.show();
				this._reloadDialogOpened = true;
			}
		},

		checkReloadRequired: function() {
			// check if UMC needs a browser reload and prompt the user to reload
			return this.urlExists('umc/').then(undefined, lang.hitch(this, function(e) {
				if (e.response.status === 404) {
					this.askToReload();
				}
			}));
		},

		_resetCallbacks: [],
		registerOnReset: function(/*Function*/ callback) {
			this._resetCallbacks.push(callback);
		},

		resetModules: function() {
			topic.publish('/umc/module/reset');
			topic.publish('/umc/actions', 'session', 'reset');
			array.forEach(this._resetCallbacks, function(callback) {
				if (typeof callback !== 'function') {
					// only execute functions
					return;
				}
				try {
					callback();
				}
				catch(e) { }
			});
		},

		urlExists: function(moduleURL) {
			return basexhr("HEAD", {url: require.toUrl(moduleURL)});
		},

		// handler class for long polling scenario
		_PollingHandler: function(url, content, finishedDeferred, args) {
			var opts = args.longPollingOptions;
			return {
				finishedDeferred: finishedDeferred,

				// url to which
				url: url,

				// JSON data that is being sent
				content: content,

				// in seconds, timeout that will be passed over to the XHR post command
				xhrTimeout: lang.getObject('xhrTimeout', false, opts) || 300,

				// in seconds, will be multiplied with the number of retries
				timeoutRetry: lang.getObject('timeoutRetry', false, opts) || 2,

				// in seconds, maximal time interval to wait between reestablishing a connection
				maxTimeoutRetry: lang.getObject('maxTimeoutRetry', false, opts) || 30,

				// in seconds, specifies the time interval in which a request is considered
				// to have failed
				failureInterval: lang.getObject('failureInterval', false, opts) || 10,

				// number of seconds after which an information ist displayed to the user
				// in case the connection could not be established; if negative, no message
				// will be shown.
				messageInterval: lang.getObject('messageInterval', false, opts) || 120,

				// message that is displayed to the user in case the
				message: lang.getObject('message', false, opts) || _('So far, the connection to the server could not be established after {time} seconds. This can be a normal behavior. In any case, the process will continue to establish the connection.'),

				// set to true, the _PollingHandler will not try a login
				noLogin: false,

				_startTime: (new Date()).getTime(),

				_lastRequestTime: 0,

				_firstErrorTime: 0,

				_nErrors: 0,

				// information dialog to display to the user
				_dialog: new Dialog({
					title: _('Information'),
					style: 'max-width: 400px'
				}),

				sendRequest: function() {
					// switch off the automatic check for session timeout...
					// the problem here is as follows, we do not receive a response,
					// therefore our session may expire, however, the server will
					// renew the session with each valid request that it receives
					tools.holdSession();

					// send AJAX command
					this._lastRequestTime = (new Date()).getTime();
					xhr.post(this.url, {
						data: this.content,
						preventCache: true,
						handleAs: 'json',
						headers: lang.mixin({
							'Accept-Language': i18nTools.defaultLang(),
							'Accept': 'application/json; q=1.0, text/html; q=0.3; */*; q=0.1',
							'X-XSRF-Protection': tools.getCookies().sessionID,
							'Content-Type': 'application/json'
						}, args.headers),
						withCredentials: args.withCredentials,
						timeout: 1000 * this.xhrTimeout
					}).then(lang.hitch(this, function(data) {
						// request finished
						tools._updateSession();
						this._dialog.hide();
						this._dialog.destroyRecursive();
						this.finishedDeferred.resolve(data);
					}), lang.hitch(this, function(error) {
						var info = tools.parseError(error);
						info.exception = error;

						if (!this.noLogin && 401 === info.status) {
							// command was rejected, user is not authorized... continue to poll after successful login
							var deferred = login.handleAuthenticationError(info);
							if (deferred) {
								deferred.then(lang.hitch(this, 'sendRequest'));
								return;
							}
						}

						// error case
						var elapsedTime = ((new Date()).getTime() - this._lastRequestTime) / 1000.0;
						if (elapsedTime < this.failureInterval) {
							// the server could not been reached within a short time interval
							// -> that is an error
							++this._nErrors;
							if (this._nErrors === 1) {
								// log the error time
								this._firstErrorTime = (new Date()).getTime();
							}
							var elapsedErrorTime = ((new Date()).getTime() - this._firstErrorTime) / 1000.0;
							if (this.messageInterval > 0 && elapsedErrorTime > this.messageInterval && !this._dialog.get('open')) {
								// show message to user
								this._dialog.set('content', lang.replace(this.message, { time: Math.round(elapsedErrorTime) }));
								this._dialog.show();
							}
						}
						else {
							// probably the request got a timeout
							this._nErrors = 0;
							this._firstErrorTime = 0;
						}

						// try again
						setTimeout(lang.hitch(this, 'sendRequest'), 1000 * Math.min(this.timeoutRetry * this._nErrors, this.maxTimeoutRetry));
					}));
				}
			};
		},

		umcpCommand: function(
			/*String*/ command,
			/*Object?*/ dataObj,
			/*Object|Boolean?*/ handleErrors,
			/*String?*/ flavor,
			/*Object?*/ longPollingOptions,
			/*Object?*/ args) {

			// build the URL for the UMCP command
			if (!(/^(get\/|set$|auth|logout(\/|$)|saml(\/|$))/i).test(command)) {
				command = 'command/' + command;
			}

			// build message body
			var _body = {
				 options: dataObj || {}
			};
			if (typeof flavor === "string") {
				_body.flavor = flavor;
			}

			return this._request(lang.mixin({
				url: '/univention/' + command,
				data: _body,
				errorHandler: this.__getErrorHandler(handleErrors),
				flavor: flavor,
				headers: {},
				withCredentials: false,
				longPollingOptions: longPollingOptions
			}, args || {}));
		},

		_request: function(args) {
			// summary:
			//		Encapsulates an AJAX call for a given UMCP command.
			// returns:
			//		A deferred object.

			// set default values for parameters
			var url = args.url ? args.url : '/univention/' + args.type + (args.command ? '/' + args.command : '');
			var body = args.body;
			if (args.data !== undefined) {
				body = args.data;
				tools.removeRecursive(body, function(key) {
					// hidden properties or un-jsonable values
					return key.substr(0, 18) === '_univention_cache_';
				});
				body = json.stringify(body);
			}

			if (args.longPollingOptions) {
				// long polling AJAX call

				// new handler
				var finishedDeferred = new Deferred();
				var handler = new this._PollingHandler(url, body, finishedDeferred, args);
				handler.sendRequest();

				return finishedDeferred; // Deferred
			}
			else {
				// normal AJAX call
				var call = xhr.post(url, {
					data: body,
					handleAs: 'json',
					headers: lang.mixin({
						'Accept-Language': i18nTools.defaultLang(),
						'Accept': 'application/json; q=1.0, text/html; q=0.3; */*; q=0.1',
						'X-XSRF-Protection': tools.getCookies().sessionID,
						'Content-Type': 'application/json'
					}, args.headers),
					withCredentials: args.withCredentials
				});

				call = call.then(function(data) {
					tools._updateSession();
					return data;
				});

				// handle XHR errors unless not specified otherwise
				if (args.errorHandler) {
					call = call.then(function(data) {
						args.errorHandler.success(data);
						return data;
					}, lang.hitch(this, function(error) {
						var info = tools.parseError(error);
						info.exception = error;
						var deferred = args.errorHandler.error(info);
						if (!deferred) {
							throw error;
						}
						return deferred.then(lang.hitch(this, function() {
							return this._request.apply(this, [args]);
						}));
					}));
				}

				// return the Deferred object
				return call; // Deferred
			}
		},

		__getErrorHandler: function(handleErrors) {
			var custom = {};
			if (handleErrors === false) {
				custom = {
					displayErrors: false,
					displayMessages: false
				};
			} else if (handleErrors && handleErrors.onValidationError) {
				custom = {
					display422: function(info) {
						handleErrors.onValidationError(info.message, info.result);
					}
				};
			} else if (typeof handleErrors === 'object') {
				custom = handleErrors;
			}

			var errorHandler = lang.mixin({
				displayMessages: true,
				displayErrors: true,

				401: function() {
					return login.handleAuthenticationError.apply(login, arguments);
				},

				display422: function(info) {
					var message = entities.encode(info.message) + ':<br>';
					var formatter = function(result) {
						message += '<ul>';
						tools.forIn(result, function(key, value) {
							if (typeof value === 'object') {
								message += '<li>' + entities.encode(key);
								formatter(value);
								message += '</li>';
								return;
							}
							message += '<li>' + entities.encode(key) + ': ' + entities.encode(value) + '</li>';
						});
						message += '</ul>';
					};
					formatter(info.result);
					dialog.alert(message, tools._statusMessages[info.status]);
				},

				success: function(data) {
					if (!this.displayMessages) {
						return;
					}
					// do not modify the data!
					if (data && data.message) {
						if (parseInt(data.status, 10) === 200) {
							dialog.notify(entities.encode(data.message));
						} else {
							dialog.alert(entities.encode(data.message));
						}
					}
				},

				error: function(info) {

					this.displayError(info);

					if (this[info.status]) {
						return this[info.status](info);
					}
				},

				displayError: function(info) {
					if (!this.displayErrors) {
						return;
					}
					topic.publish('/umc/actions', 'error', info.status || 'unknown');
					var status = info.status;
					var message = info.message;

					if (this['display' + status]) {
						this['display' + status](info);
						return;
					}

					if (status === 401) {
						return;
					}

					if (info.result && info.result.display_feedback) {
						if (info.result.title) {
							info.title = info.result.title;
						}
						info.traceback = '';
						this.displayTraceback(info);
					} else if (info.traceback) {
						this.displayTraceback(info);
					} else if (info.title) {
						// all other cases
						dialog.alert('<p>' + entities.encode(info.title) + '</p>' + (message ? '<p>' + _('Server error message:') + '</p><p class="umcServerErrorMessage">' + entities.encode(message).replace(/\n/g, '<br/>') + '</p>' : ''), _('An error occurred'));
					} else if (status) {
						// unknown status code .. should not happen
						dialog.alert(_('An unknown error with status code %s occurred while connecting to the server, please try again later.', status));
					} else {
						// probably server timeout, could also be a different error
						dialog.alert(_('An error occurred while connecting to the server, please try again later.'));
					}
				},

				displayTraceback: function(info) {
					topic.publish('/umc/actions', 'error', 'traceback');
					tools.showTracebackDialog(info.message + '\n\n' + info.traceback, info.title);
				}
			}, custom);
			return errorHandler;
		},

		umcpProgressCommand: function(
			/*Object*/ progressBar,
			/*String*/ commandStr,
			/*Object?*/ dataObj,
			/*Object?*/ errorHandler,
			/*String?*/ flavor,
			/*Object?*/ longPollingOptions) {

			// summary:
			//		Sends an initial request and expects a "../progress" function
			// returns:
			//		A deferred object.
			var deferred = new Deferred();
			this.umcpCommand(commandStr, dataObj, errorHandler, flavor, longPollingOptions).then(
				lang.hitch(this, function(data) {
					var progressID = data.result.id;
					var title = data.result.title;
					progressBar.setInfo(title);
					var allData = [];
					var splitIdx = commandStr.lastIndexOf('/');
					var progressCmd = commandStr.slice(0, splitIdx) + '/progress';
					this.umcpProgressSubCommand({
						progressCmd: progressCmd,
						progressID: progressID,
						flavor: flavor
					}).then(function() {
							deferred.resolve(allData);
					}, function() {
						deferred.reject();
					}, function(result) {
						allData = allData.concat(result.intermediate);
						if (result.percentage === 'Infinity') { // FIXME: JSON cannot handle Infinity
							result.percentage = Infinity;
						}
						progressBar.setInfo(result.title, result.message, result.percentage);
						deferred.progress(result);
						if ('result' in result) {
							deferred.resolve(result.result);
						}
					});
				}),
				function() {
					deferred.reject(arguments);
				}
			);
			return deferred;
		},

		umcpProgressSubCommand: function(props) {
			var deferred = props.deferred;
			if (deferred === undefined) {
				deferred = new Deferred();
			}
			this.umcpCommand(props.progressCmd, {'progress_id' : props.progressID}, props.errorHandler, props.flavor).then(
				lang.hitch(this, function(data) {
					deferred.progress(data.result);
					if (data.result.finished) {
						deferred.resolve();
					} else {
						setTimeout(lang.hitch(this, 'umcpProgressSubCommand', lang.mixin({}, props, {deferred: deferred}), 200));
					}
				}),
				function() {
					deferred.reject();
				}
			);
			return deferred;
		},

		// _statusMessages:
		//		A dictionary that translates a status to an error message

		_statusMessages: {
			400: _( 'Could not fulfill the request.' ),
			401: _( 'Your session has expired, please login again.' ),
			403: _( 'You are not authorized to perform this action.' ),

			404: _( 'Webfrontend error: The specified request is unknown.' ),
			406: _( 'Webfrontend error: The specified UMCP command arguments of the request are invalid.' ),
			407: _( 'Webfrontend error: The specified arguments for the UMCP module method are invalid or missing.'),
			422: _( 'Validation error' ),
			414: _( 'Specified locale is not available.' ),

			500: _( 'Internal server error.' ),
			503: _( 'Internal server error: The service is temporarily not available.' ),
			510: _( 'Internal server error: The module process died unexpectedly.' ),
			511: _( 'Internal server error: Could not connect to the module process.' ),
			512: _( 'Internal server error: The SSL server certificate is not trustworthy. Please check your SSL configurations.' ),

			551: _( 'Internal UMC protocol error: The UMCP message header could not be parsed.' ),
			554: _( 'Internal UMC protocol error: The UMCP message body could not be parsed.' ),

			590: _( 'Internal module error: An error occurred during command processing.' ),
			591: _( 'Could not process the request.' ),
			592: _( 'Internal module error: The initialization of the module caused a fatal error.' )
		},

		_parseStatus: function(stat) {
			if (typeof stat === 'number') {
				// easy -> stat is a number
				return stat;
			}
			if (typeof stat === 'string') {
				// stat is a string, i.e., it could be "400" or "400 Bad Request"... try to parse it
				try {
					return parseInt(stat, 10);
				} catch(error) {
					// parsing failed -> return 0 as fallback
					return 0;
				}
			}
			// return 0 as fallback
			return 0;
		},

		parseError: function(error) {
			var status = error.status !== undefined ? error.status : -1;
			var message = null;
			var title = null;
			var result = null;
			var traceback = null;

			var r = /<title>(.*)<\/title>/;

			if (error.response) {
				try {
					status = error.response.xhr ? error.response.xhr.status : (error.response.status !== undefined ? error.response.status : status); // status can be 0
				} catch (err) {
					// workaround for Firefox error (Bug #29703)
					status = 0;
				}
				if (error.response.data) {
					// the response contained a valid JSON object, which contents is already html escaped
					status = error.response.data.status && this._parseStatus(error.response.data.status) || status;
					message = error.response.data.message || '';
					result = error.response.data.result || null;
					title = error.response.data.title || null;
				} else {
					// no JSON was returned, probably apache returned 502 proxy error
					message = r.test(error.response.text) ? r.exec(error.response.text)[1] : '';
				}
			} else if (error.data) {
				if (error.data.xhr) {
					status = error.data.xhr.status;
				} else {
					status = error.data.status !== undefined ? error.data.status : status;
				}
				message = error.data.message || '';
				result = error.data.result || null;
				title = error.data.title || null;
			} else if(error.text) {
				message = r.test(error.text) ? r.exec(error.text)[1] : error.text;
			} else if(error.message && error.status) {
				// Uploader: errors are returned as simple JSON object { status: "XXX ...", message: "..." }
				message = error.message;
				status = error.status;
				result = error.result || null;
				title = error.title || null;
			}

			title = title || (status !== 401 ? tools._statusMessages[status] : '') || '';
			message = message || '';

			// TODO: move into the UMC-Server
			// handle tracebacks: on 500 Internal Server Error they might not contain the word 'Traceback', because not all modules use the UMC-Server error handling yet
			if (message.match(/Traceback.*most recent call.*File.*line/) || (message.match(/File.*line.*in/) && status >= 500)) {
				var index = message.indexOf('Traceback');
				if (index === -1) {
					index = message.indexOf('File');
				}
				traceback = message.substring(index);
				message = message.substring(0, index);
			}

			return {
				status: this._parseStatus(status),
				title: title,
				message: _(String(message).replace(/\%/g, '%(percent)s'), {percent: '%'}),
				traceback: traceback,
				result: result
			};
		},

		handleErrorStatus: function(error, handleErrors) {
			// deprecated function to display errors
			// only used in uvmm/GridUpdater and adtakeover
			// TODO: remove
			var info = this.parseError(error);
			info.exception = error;

			if (401 === info.status) {
				return; /*already handled*/
			}
			this.__getErrorHandler(handleErrors ? handleErrors : {}).error(info);
		},

		showTracebackDialog: function(message, statusMessage, title) {
			var readableMessage = message.split('\n');
			// reverse it. web or mail client could truncate long tracebacks. last calls are important.
			// See Bug #33798
			// But add the first line, just in case it is "The following function failed:"
			var reversedReadableMessage = lang.replace('{0}\n{1}', [readableMessage[0], readableMessage.reverse().join('\n')]);
			var feedbackBody = lang.replace("{0}\n\n1) {1}\n2) {2}\n3) {3}\n\n----------\nUCS Version: {4}\n\n{5}", [
				_('Please take a second to provide the following information:'),
				_('steps to reproduce the failure'),
				_('expected result'),
				_('actual result'),
				tools.status('ucsVersion'),
				reversedReadableMessage
			]);

			var feedbackMailto = lang.replace('mailto:{email}?body={body}&subject={subject}', {
				email: encodeURIComponent(this.status('feedbackAddress')),
				body: encodeURIComponent(entities.decode(feedbackBody)),
				subject: encodeURIComponent(this.status('feedbackSubject'))
			});
			var feedbackLabel = _('Send as email');
			var feedbackLink = '<a href="' + entities.encode(feedbackMailto) + '">' + entities.encode(feedbackLabel) + '</a>';

			var content = '<pre>' + entities.encode(message) + '</pre>';
			var hideLink = _('Hide server error message');
			var showLink = _('Show server error message');

			var titlePane = new TitlePane({
				title: showLink,
				content: content,
				'class': 'umcTracebackPane',
				open: false,
				onHide: function() { titlePane.set('title', showLink); },
				onShow: function() { titlePane.set('title', hideLink); }
			});

			var container = new ContainerWidget({});
			container.addChild(new Text({
				content: '<p>' + entities.encode(statusMessage) + '</p>'
			}));
			container.addChild(titlePane);

			var deferred = new Deferred();
			var options = [{
				name: 'close',
				label: _('Close'),
				callback: function() {
					deferred.cancel();
				}
			}, {
				name: 'as_email',
				label: feedbackLabel,
				callback: function() {
					deferred.resolve();
					window.open(feedbackMailto, '_blank');
				}
			}, {
				name: 'send',
				'default': true,
				label: _('Inform vendor'),
				callback: lang.hitch(this, function() {
					tools.sendTraceback(message, feedbackLink).then(function() {
						deferred.resolve();
					}, function() {
						deferred.reject();
					});
				})
			}];
			return dialog.confirm(container, options, title || _('An error occurred')).then(function() {
				return deferred;
			});
		},

		sendTraceback: function(traceback, feedbackLink) {
			return dialog.confirmForm({
				title: _('Send to vendor'),
				widgets: [{
					type: Text,
					name: 'help',
					content: _('Information about the error will be sent to the vendor along with some data about the operating system.')
				}, {
					type: TitlePane,
					name: 'traceback',
					title: _('Show error message'),
					'class': 'umcTracebackPane',
					style: 'display: block;',
					open: false,
					content: '<pre>' + entities.encode(traceback) + '</pre>'
				}, {
					type: TextArea,
					name: 'remark',
					label: _('Remarks (e.g. steps to reproduce) (optional)')
				}, {
					type: TextBox,
					name: 'email',
					label: _('Your email address (optional)')
				}]
			}).then(function(values) {
				values.traceback = traceback;
				return tools.umcpCommand('sysinfo/traceback', values, false).then(function() {
					dialog.alert(_('Thank you for your help'));
				}, function() {
					var alertString = _('Sending the information to the vendor failed');
					if (feedbackLink) {
						alertString += '. ' + _('You can also send the information via mail:') + ' ' + feedbackLink;
					}
					dialog.alert(alertString);
				});
			});
		},

		forIn: function(/*Object*/ obj, /*Function*/ callback, /*Object?*/ scope, /*Boolean?*/ inheritedProperties) {
			// summary:
			//		Iterate over all elements of an object.
			// description:
			//		Iterate over all elements of an object checking with hasOwnProperty()
			//		whether the element belongs directly to the object.
			//		Optionally, a scope can be defined.
			//		The callback function will be called with the parameters
			//		callback(/*String*/ key, /*mixed*/ value, /*Object*/ obj).
			// 		Returning false from within the callback function will break the loop
			//
			//		This method is similar to dojox/lang/functional/forIn where no hasOwnProperty()
			//		check is carried out.

			scope = scope || _window.global;
			for (var i in obj) {
				if (obj.hasOwnProperty(i) || inheritedProperties) {
					if ( false === callback.call(scope, i, obj[i], obj ) ) {
						break;
					}
				}
			}
		},

		mapWalk: function(/*Array*/ anArray, /*Function*/ callback, /*Object?*/ scope) {
			// summary:
			//		Equivalent to array.map(), however this function is intended to be used
			//		with multi-dimensional arrays.

			// make sure we have an array
			if (!(anArray instanceof Array)) {
				return callback.call(scope, anArray);
			}

			// clone array and walk through it
			scope = scope || _window.global;
			var res = lang.clone(anArray);
			var stack = [ res ];
			while (stack.length) {
				// new array, go through its elements
				var iarray = stack.pop();
				array.forEach(iarray, function(iobj, i) {
					if (iobj instanceof Array) {
						// put arrays on the stack
						stack.push(iobj);
					}
					else {
						// map object
						iarray[i] = callback.call(scope, iobj);
					}
				});
			}

			// return the final array
			return res;
		},

		forEachAsync: function(/*Array*/ list, /*Function*/ callback, /*Object?*/ scope, /*Integer?*/ chunkSize, /*Integer?*/ timeout) {
			// summary:
			// 		Asynchronous forEach function to process large intensive tasks.
			// description:
			//		This asynchronous forEach function allows to process large lists with
			//		computation intensive code without blocking the GUI.
			//		This is done by splitting up all data elements into chunks which are
			//		processed one after another by calling setTimeout. This allows other
			//		events to be executed in between the computationally intensive tasks.
			// list: Array
			// 		Array of elements to be processed.
			// callback: Function
			// 		Callback function that is called for each element with arguments (element, index).
			// scope: Object?
			// 		Optional scope in which the callback function is executed.
			// chunkSize: Integer?
			//		Number of elements that are processed sequentially (default=1).
			// timeout: Integer?
			//		Milliseconds to wait until the next chunk is processed (default=0).
			chunkSize = chunkSize || 1;
			scope = scope || _window.global;
			timeout = timeout || 0;

			var nChunks = Math.ceil(list.length / chunkSize);
			var nChunksDone = 0;
			var deferred = new Deferred();
			var _hasFinished = function() {
				++nChunksDone;
				if (nChunksDone >= nChunks) {
					deferred.resolve();
					return true;
				}
				return false;
			};

			var _processChunk = function(istart) {
				for (var i = istart; i < list.length && i < istart + chunkSize; ++i) {
					lang.hitch(scope, callback, list[i], i)();
				}
				if (!_hasFinished()) {
					// process next chunk asynchronously by calling setTimeout
					setTimeout(lang.hitch(scope, _processChunk, istart + chunkSize), timeout);
				}
			};

			// start processing
			setTimeout(lang.hitch(scope, _processChunk, 0), 0);

			return deferred;
		},

		assert: function(/* boolean */ booleanValue, /* string? */ message){
			// summary:
			// 		Throws an exception if the assertion fails.
			// description:
			// 		If the asserted condition is true, this method does nothing. If the
			// 		condition is false, we throw an error with a error message.
			// booleanValue:
			//		Must be true for the assertion to succeed.
			// message:
			//		A string describing the assertion.

			// throws: Throws an Error if 'booleanValue' is false.
			if(!booleanValue){
				var errorMessage = _('An assert statement failed');
				if(message){
					errorMessage += ':\n' + message;
				}

				// throw error
				var e = new Error(errorMessage);
				throw e;
			}
		},


		cmpObjects: function(/*mixed...*/) {
			// summary:
			//		Returns a comparison functor for Array.sort() in order to sort arrays of
			//		objects/dictionaries.
			// description:
			//		The function arguments specify the sorting order. Each function argument
			//		can either be a string (specifying the object attribute to compare) or an
			//		object with 'attribute' specifying the attribute to compare. Additionally,
			//		the object may specify the attributes 'descending' (boolean), 'ignoreCase'
			//		(boolean).
			//		In order to be useful for grids and sort options, the arguments may also
			//		be one single array.
			// example:
			//	|	var list = [ { id: '0', name: 'Bob' }, { id: '1', name: 'alice' } ];
			//	|	var cmp = tools.cmpObjects({
			//	|		attribute: 'name',
			//	|		descending: true,
			//	|		ignoreCase: true
			//	|	});
			//	|	list.sort(cmp);
			// example:
			//	|	var list = [ { id: '0', val: 100, val2: 11 }, { id: '1', val: 42, val2: 33 } ];
			//	|	var cmp = tools.cmpObjects('val', {
			//	|		attribute: 'val2',
			//	|		descending: true
			//	|	});
			//	|	list.sort(cmp);
			//	|	var cmp2 = tools.cmpObjects('val', 'val2');
			//	|	list.sort(cmp2);

			// in case we got a single array as argument,
			var args = arguments;
			if (1 === arguments.length && arguments[0] instanceof Array) {
				args = arguments[0];
			}

			// prepare unified ordering property list
			var order = [];
			for (var i = 0; i < args.length; ++i) {
				// default values
				var o = {
					attr: '',
					desc: 1,
					ignCase: true
				};

				// entry for ordering can by a String or an Object
				if (typeof args[i] === "string") {
					o.attr = args[i];
				}
				else if (typeof args[i] === "object" && 'attribute' in args[i]) {
					o.attr = args[i].attribute;
					o.desc = (args[i].descending ? -1 : 1);
					o.ignCase = undefined === args[i].ignoreCase ? true : args[i].ignoreCase;
				}
				else {
					// error case
					tools.assert(false, 'Wrong parameter for tools.cmpObjects(): ' + json.stringify(args));
				}

				// add order entry to list
				order.push(o);
			}

			// return the comparison function
			return function(_a, _b) {
				for (var i = 0; i < order.length; ++i) {
					var o = order[i];

					// check for lowercase (ignore not existing values!)
					var a = _a[o.attr];
					var b = _b[o.attr];
					if (o.ignCase && a && a.toLowerCase && b && b.toLowerCase) {
						a = a.toLowerCase();
						b = b.toLowerCase();
					}

					// check for lower/greater
					if (a < b) {
						return -1 * o.desc;
					}
					if (a > b) {
						return 1 * o.desc;
					}
				}
				return 0;
			};
		},

		isEqual: /* Boolean */ function(/* mixed */a, /* mixed */b) {
			// summary:
			//		recursive compare two objects(?) and return true if they are equal
			if (a === b) {
				return true;
			}
			if(typeof a !== typeof b) { return false; }

			// check whether we have arrays
			if (a instanceof Array && b instanceof Array) {
				if (a.length !== b.length) {
					return false;
				}
				for (var i = 0; i < a.length; ++i) {
					if (!tools.isEqual(a[i], b[i])) {
						return false;
					}
				}
				return true;
			}
			if (typeof a === "object" && typeof b === "object" && !(a === null || b === null)) {
				var allKeys = lang.mixin({}, a, b);
				var result = true;
				tools.forIn(allKeys, function(key) {
						result = result && tools.isEqual(a[key], b[key]);
						return result;
				});
				return result;
			}
			return a === b;
		},

		// taken from: http://stackoverflow.com/a/9221063
		_regIPv4:  /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))$/,
		_regIPv6: /^((([0-9A-Fa-f]{1,4}:){7}([0-9A-Fa-f]{1,4}|:))|(([0-9A-Fa-f]{1,4}:){6}(:[0-9A-Fa-f]{1,4}|((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3})|:))|(([0-9A-Fa-f]{1,4}:){5}(((:[0-9A-Fa-f]{1,4}){1,2})|:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3})|:))|(([0-9A-Fa-f]{1,4}:){4}(((:[0-9A-Fa-f]{1,4}){1,3})|((:[0-9A-Fa-f]{1,4})?:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9A-Fa-f]{1,4}:){3}(((:[0-9A-Fa-f]{1,4}){1,4})|((:[0-9A-Fa-f]{1,4}){0,2}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9A-Fa-f]{1,4}:){2}(((:[0-9A-Fa-f]{1,4}){1,5})|((:[0-9A-Fa-f]{1,4}){0,3}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9A-Fa-f]{1,4}:){1}(((:[0-9A-Fa-f]{1,4}){1,6})|((:[0-9A-Fa-f]{1,4}){0,4}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(:(((:[0-9A-Fa-f]{1,4}){1,7})|((:[0-9A-Fa-f]{1,4}){0,5}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:)))(%.+)?$/,
		
		_regFQDN: /^(?=.{1,254}$)((?=[a-z0-9-]{1,63}\.)[a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,63}$/i,
		_regHostname: /^(?=[a-z0-9-]{1,63}$)([a-z0-9]+(-[a-z0-9]+)*)+$/i,

		isIPv4Address:function(ip) {
			return tools._regIPv4.test(ip);
		},

		isIPv6Address: function(ip) {
			return tools._regIPv6.test(ip);
		},

		isIPAddress: function(ip) {
			return tools.isIPv4Address(ip) || tools.isIPv6Address(ip);
		},

		isFQDN: function(fqdn) {
			return tools._regFQDN.test(fqdn);
		},

		isHostname: function(hostname) {
			return tools._regHostname.test(hostname);
		},

		_existingIconClasses: {},

		getIconClass: function(icon, size, prefix, cssStyle) {
			icon = icon || '';
			cssStyle = cssStyle || '';

			// check whether the css rule for the given icon has already been added
			var values = {
				s: size || 16,
				icon: icon,
				dir: 'scalable'
			};

			if (size === 'scalable') {
				values.s = '';
			}

			if (/\.png$/.test(icon)) {
				// adjust the dir name for PNG images
				values.dir = lang.replace('{s}x{s}', values);
			}

			var iconClass;
			if (icon.substr(0, 4) === ('http')) {
				// absolute path. use!
				// iconClass must be modified to the icon file name
				values.url = icon;
				values.icon = icon.replace(/\.\w*$/, '').replace(/.*\//, '');
				iconClass = lang.replace('abs{s}-{icon}', values);
			} else {
				// split filename and filename suffix
				var reSplitFilename = /(.*?)(?:\.([^.]+))?$/;
				var filenameParts = reSplitFilename.exec(icon);
				values.suffix = filenameParts[2] || 'svg';
				values.icon = filenameParts[1];

				// search in local icons directory
				values.url = require.toUrl('dijit/themes/umc/icons');
				values.url = lang.replace('{url}/{dir}/{icon}.{suffix}', values);
				iconClass = lang.replace('icon{s}-{icon}', values);
			}

			// prefix handling
			if (prefix) {
				iconClass = lang.replace('{prefix}-{class}', {
					prefix: prefix,
					'class': iconClass
				});
			}

			// create rule if it has not already been created
			if (!(iconClass in this._existingIconClasses)) {
				try {
					// add dynamic style sheet information for the given icon
					var css = lang.replace(
						'background: no-repeat;' +
						(size === 'scalable' ? '' : 'width: {s}px; height: {s}px;') +
						'background-image: url("{url}") !important;' +
						cssStyle,
						values);
					styles.insertCssRule('.' + iconClass, css);

					// remember that we have already added a rule for the icon
					this._existingIconClasses[iconClass] = true;
				}
				catch (error) {
					console.log(lang.replace("ERROR: Could not create CSS information for the icon name '{icon}' of size {s}", values));
				}
			}
			return iconClass;
		},

		getUserPreferences: function() {
			var deferred = new Deferred();
			tools.umcpCommand('get/user/preferences', null, false).then(
				function(data) {
					deferred.resolve(data.preferences);
				},
				function(data) {
					deferred.cancel(data);
				}
			);
			return deferred;
		},

		setUserPreference: function(preferences) {
			return tools.umcpCommand('set', {
				user: { preferences: preferences }
			}, false);
		},

		removeRecursive: function(obj, func) {
			// summary:
			//	Removes recursively from an Object
			//	walks recursively over Arrays and Objects
			tools.forIn(obj, function(key, value) {
				if (func(key)) {
					delete obj[key];
				} else {
					// [] instanceof Object is true, but we test for Array because of readability
					if (value && typeof value !== "function" && (value instanceof Array || value instanceof Object)) {
						tools.removeRecursive(value, func);
					}
				}
			});
		},

		delegateCall: function(/*Object*/ self, /*Arguments*/ args, /*Object*/ that) {
			// summary:
			//		Delegates a method call into the scope of a different object.
			var m = self.getInherited(args);
			m.apply(that, args);
		},

		_userPreferences: null, // internal reference to the user preferences

		// internal array with default values for all preferences
		_defaultPreferences: {
			//confirm: true
		},

		preferences: function(/*String|Object?*/ param1, /*AnyType?*/ value) {
			// summary:
			//		Convenience function to set/get user preferences.
			//		All preferences will be store in a cookie (in JSON format).
			// returns:
			//		If no parameter is given, returns dictionary with all preference
			//		entries. If one parameter of type String is given, returns the
			//		preference for the specified key. If one parameter is given which
			//		is an dictionary, will set all key-value pairs as specified by
			//		the dictionary. If two parameters are given and
			//		the first is a String, the function will set preference for the
			//		key (paramater 1) to the value as specified by parameter 2.

			// make sure the user preferences are cached internally
			var cookieStr = '';
			if (!this._userPreferences) {
				// not yet cached .. get all preferences via cookies
				this._userPreferences = lang.clone(this._defaultPreferences);
				cookieStr = cookie('UMCPreferences') || '{}';
				lang.mixin(this._userPreferences, json.parse(cookieStr));
			}

			// no arguments, return full preference object
			if (0 === arguments.length) {
				return this._userPreferences; // Object
			}
			// only one parameter, type: String -> return specified preference
			if (1 === arguments.length && typeof param1 === "string") {
				if (param1 in this._defaultPreferences) {
					return this._userPreferences[param1]; // Boolean|String|Integer
				}
				return undefined;
			}

			// backup the old preferences
			var oldPrefs = lang.clone(this._userPreferences);

			// only one parameter, type: Object -> set all parameters as specified in the object
			if (1 === arguments.length) {
				// only consider keys that are defined in defaultPreferences
				tools.forIn(this._defaultPreferences, lang.hitch(this, function(key) {
					if (key in param1) {
						this._userPreferences[key] = param1[key];
					}
				}));
			}
			// two parameters, type parameter1: String -> set specified user preference
			else if (2 === arguments.length && typeof param1 === "string") {
				// make sure preference is in defaultPreferences
				if (param1 in this._defaultPreferences) {
					this._userPreferences[param1] = value;
				}
			}
			// otherwise throw error due to incorrect parameters
			else {
				tools.assert(false, 'tools.preferences(): Incorrect parameters: ' + arguments);
			}

			// publish changes in user preferences
			tools.forIn(this._userPreferences, function(key, val) {
				if (val !== oldPrefs[key]) {
					// entry has changed
					topic.publish('/umc/preferences/' + key, val);
				}
			});

			// set the cookie with all preferences
			cookieStr = json.stringify(this._userPreferences);
			cookie('UMCPreferences', cookieStr, { expires: 100, path: '/univention/' } );
			return; // undefined
		},

		ucr: function(/*String|String[]*/ query) {
			// summary:
			//		Function that fetches with the given query the UCR variables.
			// query: String|String[]
			//		Query string (or array of query strings) that is matched on the UCR variable names.
			// return: Deferred
			//		Returns a Deferred that expects a callback to which is passed
			//		a dict of variable name -> value entries.

			return this.umcpCommand('get/ucr',  query  instanceof Array ? query : [ query ] ).then(function(data) {
				return data.result;
			});
		},

		isFalse: function(/*mixed*/ input) {
			if (typeof input === "string") {
				switch (input.toLowerCase()) {
					case 'no':
					case 'not':
					case 'false':
					case '0':
					case 'disable':
					case 'disabled':
					case 'off':
						return true;
				}
			}
			if (false === input || 0 === input || null === input || undefined === input || '' === input) {
				return true;
			}
			return false;
		},

		isTrue: function(/*mixed*/ input) {
			//('yes', 'true', '1', 'enable', 'enabled', 'on')
			return !this.isFalse(input);
		},

		isFreeLicense: function(/*string*/ licenseValue) {
			return licenseValue === 'Free for personal use edition' || licenseValue === 'UCS Core Edition';
		},

		explodeDn: function(dn, noTypes) {
			// summary:
			//		Splits the parts of an LDAP DN into an array.
			// dn: String
			//		LDAP DN as String.
			// noTypes: Boolean?
			//		If set to true, the type part ('.*=') of each LDAP DN part will be removed.

			var res = [];
			if (typeof dn === "string") {
				res = dn.split(',');
			}
			if (noTypes) {
				res = array.map(res, function(x) {
					return x.slice(x.indexOf('=')+1);
				});
			}
			return res;
		},

		ldapDn2Path: function( dn, base ) {
			var base_list = this.explodeDn( base, true );
			var path = '';

			dn = dn.slice( 0, - ( base.length + 1 ) );
			var dn_list = this.explodeDn( dn, true ).slice( 1 );

			// format base
			path = base_list.reverse().join( '.' ) + ':/';
			if ( dn_list.length ) {
				path += dn_list.reverse().join( '/' );
			}

			return path;
		},

		inheritsFrom: function(/*Object*/ _o, /*String*/ c) {
			// summary:
			//		Returns true in case object _o inherits from class c.
			var bases = lang.getObject('_meta.bases', false, _o.constructor);
			if (!bases) {
				// no dojo object
				return false;
			}

			var matched = false;
			array.forEach(bases, function(ibase) {
				if (ibase.prototype.declaredClass === c) {
					matched = true;
					return false;
				}
			});
			return matched;
		},

		getParentModule: function(/*_WidgetBase*/ widget) {
			// summary:
			//		Return the enclosing module of the widget.

			if (!widget || typeof widget.getParent !== 'function') {
				return null;
			}

			// recursively climb up the DOM
			var parentWidget = widget.getParent();
			while (parentWidget) {
				if (this.inheritsFrom(parentWidget, 'umc.widgets._ModuleMixin')) {
					// found the parent module
					return parentWidget;
				}
				parentWidget = parentWidget.getParent();
			}
			return null;
		},

		capitalize: function(/*String*/ str) {
			// summary:
			//		Return a string with the first letter in upper case.
			if (typeof str !== "string") {
				return str;
			}
			return str.slice(0, 1).toUpperCase() + str.slice(1);
		},

		stringOrArray: function(/*String|String[]*/ input) {
			// summary:
			//		Transforms a string to an array containing the string as element
			//		and if input is an array, the array is not modified. In any other
			//		case, the function returns an empty array.

			if (typeof input === "string") {
				return [ input ];
			}
			if (input instanceof Array) {
				return input;
			}
			return [];
		},

		_regFuncAmdStyle: /^javascript:\s*(\w+(\/\w+)*)(:(\w+))?$/,
		_regFuncDotStyle: /^javascript:\s*(\w+(\.\w+)*)$/,

		stringOrFunction: function(/*String|Function*/ input, /*Function?*/ umcpCommand) {
			// summary:
			//		Transforms a string starting with 'javascript:' to a javascript
			//		function, otherwise to an UMCP command function (if umcpCommand)
			//		is specified, and leaves a function a function.
			//		Anything else will be converted to a dummy function.
			// example:
			//		Dot-notation, calling the function foo.bar():
			// |	stringOrFunction('javascript:foo.bar');
			//		Calling the AMD module foo/bar which is expected to be a function:
			// |	stringOrFunction('javascript:foo/bar');
			//		Calling the function doit() of the AMD module foo/bar:
			// |	stringOrFunction('javascript:foo/bar:doit');

			if (typeof input === "function") {
				return input;
			}
			if (typeof input === "string") {
				var match = this._regFuncDotStyle.exec(input);
				var deferred = null;
				if (match) {
					// javascript function in dot style
					return lang.getObject(match[1]);
				}
				match = this._regFuncAmdStyle.exec(input);
				if (match) {
					// AMD module
					deferred = new Deferred();
					try {
						require([match[1]], function(module) {
							if (match[4]) {
								// get the function of the module
								deferred.resolve(module[match[4]]);
							}
							else{
								// otherwise get the full module
								deferred.resolve(module);
							}
						});
					} catch(error) {
						deferred.reject(error);
					}
					// wrapper function which waits for the loaded AMD module
					return function() {
						var args = arguments;
						return deferred.then(function(func) {
							return func.apply(this, args);
						}, function() {});
					};
				}
				if (umcpCommand) {
					// we have a reference to an ucmpCommand, we can try to execute the string as an
					// UMCP command... return function that is ready to query dynamic values via UMCP
					return function(params) {
						return umcpCommand(input, params).then(function(data) {
							// only return the data array
							return data.result;
						});
					};
				}

				// print error message
				console.log('ERROR: The string could not be evaluated as javascript code. Ignoring error: ' + input);
			}

			// return dummy function
			return function() {};
		},

		openRemoteSession: function(/*string*/ host) {

			var remoteWin;
			if (this.isTrue(this.status('umcWebSsoNewwindow'))) {
				// open window immediately, so the window is part of the click event and is not counted as popup
				remoteWin = window.open('', '_blank', 'location=yes,menubar=yes,status=yes,toolbar=yes,scrollbars=yes', false);
			}

			var jumpToUrl = lang.hitch(this, function(url) {
				console.log('openRemoteSession:', url);
				if (remoteWin) {
					// use pre-opened window
					remoteWin.location = url;
				} else {
					window.location.replace(url);
				}
			});

			var port = window.location.port ? ':' + window.location.port : '';
			jumpToUrl(window.location.protocol + '//' + host + port + '/univention/management/');
		},

		defer: function(func, waitingTime) {
			// summary:
			//		Defers the execution of the given function for a specified
			//		amount of milliseconds.
			// func: Function
			// waitingTime: Integer
			// 		Milliseconds how long the execution of the function will be
			// 		deferred. Default value is 0.
			// returns:
			//		A deferred object with the return value of the given function.
			waitingTime = waitingTime || 0;
			var deferred = new Deferred();
			setTimeout(function() {
				if (!deferred.isCanceled()) {
					deferred.resolve();
				}
			}, waitingTime);
			var returnDeferred = deferred.then(function() {
				return func();
			});
			return returnDeferred;
		},

		linkToModule: function(/*Object*/ props) {
			// summary:
			// 		returns a HTML <a> tag which opens a specific given UMC module
			// 		or null if the module doesn't exists
			// module: String
			// flavor: String?
			// props: Object?
			// linkName: String?
			var moduleId = props.module;
			var moduleFlavor = props.flavor;

			var module = require('umc/app').getModule(moduleId, moduleFlavor);
			if (!module) {
				return null;
			}

			var linkName = string.substitute(props.linkName || _('"${moduleName}" module'), { moduleName: module.name });
			var args = {
				module: json.stringify(moduleId).replace(/'/g, '\\"'),
				flavor: json.stringify(moduleFlavor || null).replace(/'/g, '\\"'),
				props: json.stringify(props.props || {}).replace(/'/g, '\\"'),
				link: linkName
			};

			return lang.replace('<a href="javascript:void(0)" onclick=\'require("umc/app").openModule({module}, {flavor}, {props})\'>{link}</a>', args);
		}
	});

	lang.setObject('umc.tools', tools);
	return tools;
});
