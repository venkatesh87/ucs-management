# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  base class for the handlers
#
# Copyright 2004-2017 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

import copy
import types
import re
import time
import ldap
import ipaddr
from ldap.filter import filter_format
from ldap.dn import explode_rdn, explode_dn, escape_dn_chars

import univention.debug

import univention.admin.filter
import univention.admin.uldap
import univention.admin.mapping
import univention.admin.modules
import univention.admin.uexceptions
import univention.admin.localization
import univention.admin.syntax
from univention.admin import configRegistry
from univention.admin.uldap import DN
try:
	import univention.lib.admember
	_prevent_to_change_ad_properties = univention.lib.admember.is_localhost_in_admember_mode()
except ImportError:
	univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, "Failed to import univention.lib.admember")
	_prevent_to_change_ad_properties = False

translation = univention.admin.localization.translation('univention/admin/handlers')
_ = translation.translate

# global caching variable
if configRegistry.is_true('directory/manager/samba3/legacy', False):
	s4connector_present = False
elif configRegistry.is_false('directory/manager/samba3/legacy', False):
	s4connector_present = True
else:
	s4connector_present = None


def disable_ad_restrictions(disable=True):
	global _prevent_to_change_ad_properties
	_prevent_to_change_ad_properties = disable


class base(object):

	def __init__(self, co, lo, position, dn='', superordinate=None):
		self.co = co
		self.lo = lo
		self.dn = dn
		self.superordinate = superordinate

		self.set_defaults = 0
		if not self.dn:  # this object is newly created and so we can use the default values
			self.set_defaults = 1

		if not hasattr(self, 'position'):
			self.position = position
		if not hasattr(self, 'info'):
			self.info = {}
		if not hasattr(self, 'oldinfo'):
			self.oldinfo = {}
		if not hasattr(self, 'policies'):
			self.policies = []
		if not hasattr(self, 'oldpolicies'):
			self.oldpolicies = []
		if not hasattr(self, 'policyObjects'):
			self.policyObjects = {}
		self.__no_default = []

		if not self.position:
			self.position = univention.admin.uldap.position(lo.base)
			if dn:
				self.position.setDn(dn)
		self._open = False
		self.options = []
		self.old_options = []
		self.alloc = []

	def open(self):
		self._open = True

	def save(self):
		'''saves current state as old state'''

		self.oldinfo = copy.deepcopy(self.info)
		self.oldpolicies = copy.deepcopy(self.policies)
		self.options = list(set(self.options))
		self.old_options = []
		if self.exists():
			self.old_options = copy.deepcopy(self.options)

	def diff(self):
		'''returns differences between old and current state'''
		changes = []

		for key, prop in self.descriptions.items():
			null = [] if prop.multivalue else None
			# remove properties which are disabled by options
			if prop.options and not set(prop.options) & set(self.options):
				if self.oldinfo.get(key, null) not in (null, None):
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "simpleLdap.diff: key %s not valid (option not set)" % key)
					changes.append((key, self.oldinfo[key], null))
				continue
			if (self.oldinfo.get(key) or self.info.get(key)) and self.oldinfo.get(key, null) != self.info.get(key, null):
				changes.append((key, self.oldinfo.get(key, null), self.info.get(key, null)))

		return changes

	def hasChanged(self, key):
		'''checks if the given attribute(s) was (were) changed; key can either be a
		string (scalar) or a list'''

		if isinstance(key, (list, tuple)):
			return any(self.hasChanged(i) for i in key)
		if (not self.oldinfo.get(key, '') or self.oldinfo[key] == [''] or self.oldinfo[key] == []) \
			and (not self.info.get(key, '') or self.info[key] == [''] or self.info[key] == []):
			return False

		return not univention.admin.mapping.mapCmp(self.mapping, key, self.oldinfo.get(key, ''), self.info.get(key, ''))

	def ready(self):
		'''checks if all properties marked required are set'''

		missing = []
		for name, p in self.descriptions.items():
			# skip if this property is not present in the current option set
			if p.options and not set(p.options) & set(self.options):
				continue

			if p.required and (not self[name] or (isinstance(self[name], list) and self[name] == [''])):
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "property %s is required but not set." % name)
				missing.append(name)
		if missing:
			raise univention.admin.uexceptions.insufficientInformation(_('The following properties are missing:\n%s') % ('\n'.join(missing),))

		# when creating a object make sure that its position is underneath of its superordinate
		if not self.exists() and self.position and self.superordinate:
			if not self._ensure_dn_in_subtree(self.superordinate.dn, self.position.getDn()):
				raise univention.admin.uexceptions.insufficientInformation(_('The position must be in the subtree of the superordinate.'))

		self._validate_superordinate()

		return True

	def has_key(self, key):
		try:
			p = self.descriptions[key]
		except KeyError:
			return False
		if p.options:
			return bool(set(p.options) & set(self.options))
		return True

	def __setitem__(self, key, value):
		def _changeable():
			yield self.descriptions[key].editable
			if not self.descriptions[key].may_change:
				yield key not in self.oldinfo or self.oldinfo[key] == value
			# if _prevent_to_change_ad_properties:  # FIXME: users.user.object.__init__ modifies firstname and lastname by hand
			#	yield not (self.descriptions[key].readonly_when_synced and self._is_synced_object() and self.exists())

		# property does not exist
		if not self.has_key(key):
			# don't set value if the option is not enabled
			try:
				self.descriptions[key]
			except KeyError:
				# raise univention.admin.uexceptions.noProperty(key)
				raise
			return
		# attribute may not be changed
		elif not all(_changeable()):
			raise univention.admin.uexceptions.valueMayNotChange(_('key=%(key)s old=%(old)s new=%(new)s') % {'key': key, 'old': self[key], 'new': value})
		# required attribute may not be removed
		elif self.descriptions[key].required and not value:
			raise univention.admin.uexceptions.valueRequired, _('The property %s is required') % self.descriptions[key].short_description
		# do nothing
		if self.info.get(key, None) == value:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'values are identical: %s:%s' % (key, value))
			return

		if self.info.get(key, None) == self.descriptions[key].default(self):
			self.__no_default.append(key)

		if self.descriptions[key].multivalue:

			# make sure value is list
			if isinstance(value, basestring):
				value = [value]
			elif not isinstance(value, list):
				raise univention.admin.uexceptions.valueInvalidSyntax(key)

			self.info[key] = []
			for v in value:
				if not v:
					continue
				err = ""
				p = None
				try:
					s = self.descriptions[key].syntax
					p = s.parse(v)

				except univention.admin.uexceptions.valueError, emsg:
					err = emsg
				if not p:
					if not err:
						err = ""
					try:
						raise univention.admin.uexceptions.valueInvalidSyntax, "%s: %s" % (key, err)
					except UnicodeEncodeError, e:  # raise fails if err contains umlauts or other non-ASCII-characters
						raise univention.admin.uexceptions.valueInvalidSyntax(self.descriptions[key].short_description)
				self.info[key].append(p)

		elif not value and key in self.info:
			del self.info[key]

		elif value:
			err = ""
			p = None
			try:
				s = self.descriptions[key].syntax
				p = s.parse(value)
			except univention.admin.uexceptions.valueError, e:
				err = e
			if not p:
				if not err:
					err = ""
				try:
					raise univention.admin.uexceptions.valueInvalidSyntax, "%s: %s" % (self.descriptions[key].short_description, err)
				except UnicodeEncodeError, e:  # raise fails if err contains umlauts or other non-ASCII-characters
					raise univention.admin.uexceptions.valueInvalidSyntax, "%s" % self.descriptions[key].short_description
			self.info[key] = p

	def __getitem__(self, key):
		_d = univention.debug.function('admin.handlers.base.__getitem__ key = %s' % key)
		if not key:
			return None

		if key in self.info:
			if self.descriptions[key].multivalue and not isinstance(self.info[key], list):
				# why isn't this correct in the first place?
				self.info[key] = [self.info[key]]
			return self.info[key]
		elif key not in self.__no_default and self.descriptions[key].editable:
			self.info[key] = self.descriptions[key].default(self)
			return self.info[key]
		elif self.descriptions[key].multivalue:
			return []
		else:
			return None

	def get(self, key, default=None):
		return self.info.get(key, default)

	def __contains__(self, key):
		return key in self.descriptions

	def keys(self):
		return self.descriptions.keys()

	def items(self):
		# return all items which belong to the current options - even if they are empty
		return [(key, self[key]) for key in self.keys() if self.has_key(key)]

	def create(self):
		'''create object'''

		if self.exists():
			raise univention.admin.uexceptions.objectExists(self.dn)

		self._ldap_pre_ready()
		self.ready()

		return self._create()

	def modify(self, modify_childs=1, ignore_license=0):
		'''modify object'''

		if not self.exists():
			raise univention.admin.uexceptions.noObject(self.dn)

		self._ldap_pre_ready()
		self.ready()

		return self._modify(modify_childs, ignore_license=ignore_license)

	def _create_temporary_ou(self):
		name = 'temporary_move_container_%s' % time.time()

		module = univention.admin.modules.get('container/ou')
		position = univention.admin.uldap.position('%s' % self.lo.base)

		temporary_object = module.object(None, self.lo, position)
		temporary_object.open()
		temporary_object['name'] = name
		temporary_object.create()

		return 'ou=%s' % ldap.dn.escape_dn_chars(name)

	def _delete_temporary_ou_if_empty(self, temporary_ou):

		if not temporary_ou:
			return

		dn = '%s,%s' % (temporary_ou, self.lo.base)

		module = univention.admin.modules.get('container/ou')
		temporary_object = univention.admin.modules.lookup(module, None, self.lo, scope='base', base=dn, required=True, unique=True)[0]
		temporary_object.open()
		try:
			temporary_object.remove()
		except (univention.admin.uexceptions.ldapError, ldap.NOT_ALLOWED_ON_NONLEAF):
			pass

	def move(self, newdn, ignore_license=0, temporary_ou=None):
		'''move object'''
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'move: called for %s to %s' % (self.dn, newdn))

		if not (univention.admin.modules.supports(self.module, 'move') or univention.admin.modules.supports(self.module, 'subtree_move')):  # this should have been checked before, but I want to be sure...
			raise univention.admin.uexceptions.invalidOperation()

		if not self.exists():
			raise univention.admin.uexceptions.noObject()

		if _prevent_to_change_ad_properties and self._is_synced_object():
			raise univention.admin.uexceptions.invalidOperation(_('Objects from Active Directory can not be moved.'))

		goaldn = self.lo.parentDn(newdn)
		goalmodule = univention.admin.modules.identifyOne(goaldn, self.lo.get(goaldn))
		goalmodule = univention.admin.modules.get(goalmodule)
		if not goalmodule or not hasattr(goalmodule, 'childs') or not goalmodule.childs == 1:
			raise univention.admin.uexceptions.invalidOperation(_("Destination object can't have sub objects."))

		if self.dn.lower() == newdn.lower():
			if self.dn == newdn:
				raise univention.admin.uexceptions.ldapError(_('Moving not possible: old and new DN are identical.'))
			else:
				# We must use a temporary folder because OpenLDAP does not allow a rename of an container with subobjects
				temporary_ou = self._create_temporary_ou()
				new_rdn = explode_rdn(newdn)[0]
				temp_dn = '%s,%s,%s' % (new_rdn, temporary_ou, self.lo.base)
				self.move(temp_dn, ignore_license, temporary_ou)
				self.dn = temp_dn

		if self.dn.lower() == newdn.lower()[-len(self.dn):]:
			raise univention.admin.uexceptions.ldapError(_("Moving into one's own sub container not allowed."))

		if univention.admin.modules.supports(self.module, 'subtree_move'):
			# check if is subtree:
			subelements = self.lo.search(base=self.dn, scope='one', attr=[])
			if subelements:
				olddn = self.dn
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'move: found subelements, do subtree move: newdn: %s' % newdn)
				# create copy of myself
				module = univention.admin.modules.get(self.module)
				position = univention.admin.uldap.position(self.lo.base)
				position.setDn(self.lo.parentDn(newdn))
				copyobject = module.object(None, self.lo, position)
				copyobject.open()
				for key in self.keys():
					copyobject[key] = self[key]
				copyobject.policies = self.policies
				copyobject.create()
				moved = []
				try:
					for subolddn, suboldattrs in subelements:
						univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'move: subelement %s' % subolddn)
						# Convert the DNs to lowercase before the replacement. The cases might be mixed up if the python lib is
						# used by the connector, for example:
						#   subolddn: uid=user_test_h80,ou=TEST_H81,LDAP_BASE
						#   self.dn: ou=test_h81,LDAP_BASE
						#   newdn: OU=TEST_H81,ou=test_h82,$LDAP_BASE
						rdn = explode_dn(subolddn)[0]
						subolddn_dn_without_rdn_lower = self.lo.parentDn(subolddn).lower()
						subnewdn = '%s,%s' % (rdn, subolddn_dn_without_rdn_lower.replace(self.dn.lower(), newdn))
						submodule = univention.admin.modules.identifyOne(subolddn, suboldattrs)
						submodule = univention.admin.modules.get(submodule)
						subobject = univention.admin.objects.get(submodule, None, self.lo, position='', dn=subolddn)
						if not subobject or not (univention.admin.modules.supports(submodule, 'move') or univention.admin.modules.supports(submodule, 'subtree_move')):
							subold_rdn = '+'.join(explode_rdn(subolddn, 1))
							raise univention.admin.uexceptions.invalidOperation(_('Unable to move object %(name)s (%(type)s) in subtree, trying to revert changes.') % {'name': subold_rdn, 'type': univention.admin.modules.identifyOne(subolddn, suboldattrs)})
						subobject.open()
						subobject.move(subnewdn)
						moved.append((subolddn, subnewdn))
					self.remove()
					self._delete_temporary_ou_if_empty(temporary_ou)
				except:
					univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, 'move: subtree move failed, trying to move back.')
					position = univention.admin.uldap.position(self.lo.base)
					position.setDn(self.lo.parentDn(olddn))
					for subolddn, subnewdn in moved:
						submodule = univention.admin.modules.identifyOne(subnewdn, self.lo.get(subnewdn))
						submodule = univention.admin.modules.get(submodule)
						subobject = univention.admin.objects.get(submodule, None, self.lo, position='', dn=subnewdn)
						subobject.open()
						subobject.move(subolddn)
					copyobject.remove()
					self._delete_temporary_ou_if_empty(temporary_ou)
					raise
				self.dn = newdn
				return newdn
			else:
				# normal move, fails on subtrees
				res = self._move(newdn, ignore_license=ignore_license)
				self._delete_temporary_ou_if_empty(temporary_ou)
				return res

		else:
			res = self._move(newdn, ignore_license=ignore_license)
			self._delete_temporary_ou_if_empty(temporary_ou)
			return res

	def move_subelements(self, olddn, newdn, subelements, ignore_license=False):
		if subelements:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'move: found subelements, do subtree move')
			moved = []
			try:
				for subolddn, suboldattrs in subelements:
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'move: subelement %s' % subolddn)
					subnewdn = subolddn.replace(olddn, newdn)
					submodule = univention.admin.modules.identifyOne(subolddn, suboldattrs)
					submodule = univention.admin.modules.get(submodule)
					subobject = univention.admin.objects.get(submodule, None, self.lo, position='', dn=subolddn)
					if not subobject or not (univention.admin.modules.supports(submodule, 'move') or univention.admin.modules.supports(submodule, 'subtree_move')):
						subold_rdn = '+'.join(explode_rdn(subolddn, 1))
						raise univention.admin.uexceptions.invalidOperation(_('Unable to move object %(name)s (%(type)s) in subtree, trying to revert changes.') % {'name': subold_rdn, 'type': univention.admin.modules.identifyOne(subolddn, suboldattrs)})
					subobject.open()
					subobject._move(subnewdn)
					moved.append((subolddn, subnewdn))
					return moved
			except:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, 'move: subtree move failed, try to move back')
				for subolddn, subnewdn in moved:
					submodule = univention.admin.modules.identifyOne(subnewdn, self.lo.get(subnewdn))
					submodule = univention.admin.modules.get(submodule)
					subobject = univention.admin.objects.get(submodule, None, self.lo, position='', dn=subnewdn)
					subobject.open()
					subobject.move(subolddn)
				raise

	def remove(self, remove_childs=0):
		'''remove object'''

		if not self.dn or not self.lo.get(self.dn):
			raise univention.admin.uexceptions.noObject(self.dn)

		return self._remove(remove_childs)

	def get_gid_for_primary_group(self):
		gidNum = '99999'
		if self['primaryGroup']:
			try:
				gidNum = self.lo.getAttr(self['primaryGroup'], 'gidNumber', required=True)[0]
			except ldap.NO_SUCH_OBJECT:
				raise univention.admin.uexceptions.primaryGroup(self['primaryGroup'])
		return gidNum

	def get_sid_for_primary_group(self):
		try:
			sidNum = self.lo.getAttr(self['primaryGroup'], 'sambaSID', required=True)[0]
		except ldap.NO_SUCH_OBJECT:
			raise univention.admin.uexceptions.primaryGroupWithoutSamba(self['primaryGroup'])
		return sidNum

	def _update_policies(self):
		pass

	def _ldap_pre_ready(self):
		pass

	def _ldap_pre_create(self):
		self.dn = self._ldap_dn()

	def _ldap_dn(self):
		identifier = []
		for name, prop in self.descriptions.items():
			if prop.identifies:
				identifier.append((self.mapping.mapName(name), self.mapping.mapValue(name, self.info[name]), 2))
		return '%s,%s' % (ldap.dn.dn2str([identifier]), self.position.getDn())

	def _ldap_post_create(self):
		pass

	def _ldap_pre_modify(self):
		pass

	def _ldap_post_modify(self):
		pass

	def _ldap_pre_move(self, newdn):
		pass

	def _ldap_post_move(self, olddn):
		pass

	def _ldap_pre_remove(self):
		pass

	def _ldap_post_remove(self):
		pass


def _not_implemented_method(attr):
	def _not_implemented_error(self, *args, **kwargs):
		raise NotImplementedError('%s() not implemented by %s.%s().' % (attr, self.__module__, self.__class__.__name__))
	return _not_implemented_error


# add some default abstract methods
for _attr in ('_ldap_addlist', '_ldap_modlist', '_ldap_dellist', 'exists', '_move', 'cancel', '_remove', '_create', '_modify'):
	if not hasattr(base, _attr):
		setattr(base, _attr, _not_implemented_method(_attr))


class simpleLdap(base):

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes=None):
		self._exists = False
		self.exceptions = []
		base.__init__(self, co, lo, position, dn, superordinate)

		# s4connector_present is a global caching variable than can be
		# None ==> ldap has not been checked for servers with service "S4 Connector"
		# True ==> at least one server with IP address (aRecord) is present
		# False ==> no server is present
		global s4connector_present
		if s4connector_present is None:
			s4connector_present = False
			searchResult = self.lo.search('(&(|(objectClass=univentionDomainController)(objectClass=univentionMemberServer))(univentionService=S4 Connector))', attr=['aRecord'])
			s4connector_present = any(ddn for (ddn, attr) in searchResult if 'aRecord' in attr)
		self.s4connector_present = s4connector_present

		if not univention.admin.modules.modules:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'univention.admin.modules.update() was not called')
			univention.admin.modules.update()

		m = univention.admin.modules.get(self.module)
		if not hasattr(self, 'mapping'):
			self.mapping = getattr(m, 'mapping', None)
		if not hasattr(self, 'descriptions'):
			self.descriptions = getattr(m, 'property_descriptions', None)

		self.info = {}
		self.oldattr = {}
		if attributes:
			self.oldattr = attributes
		elif self.dn:
			try:
				self.oldattr = self.lo.get(self.dn, required=True)
			except ldap.NO_SUCH_OBJECT:
				raise univention.admin.uexceptions.noObject(self.dn)

		if self.oldattr:
			self._exists = True
			oldinfo = univention.admin.mapping.mapDict(self.mapping, self.oldattr)
			oldinfo = self._post_unmap(oldinfo, self.oldattr)
			self.info.update(oldinfo)

		self.policies = self.oldattr.get('univentionPolicyReference', [])
		self.__set_options()
		self.save()

		self._validate_superordinate()

	def exists(self):
		return self._exists

	def _validate_superordinate(self):
		superordinate_names = set(univention.admin.modules.superordinate_names(self.module))
		if not superordinate_names:
			return  # module has no superodinates

		if not self.dn and not self.position:
			# this check existed in all modules with superordinates, so still check it here, too
			raise univention.admin.uexceptions.insufficientInformation(_('Neither DN nor position given.'))

		if not self.superordinate:
			self.superordinate = univention.admin.objects.get_superordinate(self.module, None, self.lo, self.dn or self.position.getDn())

		if not self.superordinate:
			if superordinate_names == set(['settings/cn']):
				univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'No settings/cn superordinate was given.')
				return   # settings/cn might be misued as superordinate, don't risk currently
			raise univention.admin.uexceptions.insufficientInformation(_('No superordinate object given'))

		# check if the superordinate is of the correct object type
		if not set([self.superordinate.module]) & superordinate_names:
			raise univention.admin.uexceptions.insufficientInformation(_('The given %r superordinate is expected to be of type %s.') % (self.superordinate.module, ', '.join(superordinate_names)))

		if self.dn and not self._ensure_dn_in_subtree(self.superordinate.dn, self.lo.parentDn(self.dn)):
			raise univention.admin.uexceptions.insufficientInformation(_('The DN must be underneath of the superordinate.'))

	def _ensure_dn_in_subtree(self, parent, dn):
		while dn:
			if self.lo.lo.compare_dn(dn, parent):
				return True
			dn = self.lo.parentDn(dn)
		return False

	def call_udm_property_hook(self, hookname, module, changes=None):
		m = univention.admin.modules.get(module.module)
		if hasattr(m, 'extended_udm_attributes'):
			for prop in m.extended_udm_attributes:
				if prop.hook is not None:
					func = getattr(prop.hook, hookname, None)
					if changes is None:
						func(module)
					else:
						changes = func(module, changes)
		return changes

	def open(self):
		base.open(self)
		self.exceptions = []
		self.call_udm_property_hook('hook_open', self)
		self.save()

	def _remove_option(self, name):
		if name in self.options:
			self.options.remove(name)

	def __set_options(self):
		self.options = []
		options = univention.admin.modules.options(self.module)
		if 'objectClass' in self.oldattr:
			ocs = set(self.oldattr['objectClass'])
			for opt, option in options.iteritems():
				if not option.disabled and option.matches(ocs):
					self.options.append(opt)
		else:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'reset options to default by _define_options')
			self._define_options(options)

	def _define_options(self, module_options):
		# enable all default options
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'modules/__init__.py _define_options: reset to default options')
		for name, opt in module_options.items():
			if not opt.disabled and opt.default:
				self.options.append(name)

	def option_toggled(self, option):
		'''Checks if an option was changed. This does not work for not yet existing objects.'''
		return option in set(self.options) ^ set(self.old_options)

	def description(self):
		if self.dn:
			return '+'.join(explode_rdn(self.dn, 1))
		return 'none'

	def _post_unmap(self, info, values):
		"""This method can be overwritten to define special un-map
		methods that can not be done with the default mapping API"""
		return info

	def _post_map(self, modlist, diff):
		"""This method can be overwritten to define special map methods
		that can not be done with the default mapping API"""
		return modlist

	def _ldap_modlist(self):
		self.exceptions = []

		diff_ml = self.diff()
		ml = univention.admin.mapping.mapDiff(self.mapping, diff_ml)
		ml = self._post_map(ml, diff_ml)

		# policies
		if self.policies != self.oldpolicies:
			if 'univentionPolicyReference' not in self.oldattr.get('objectClass', []):
				ml.append(('objectClass', '', ['univentionPolicyReference']))
			ml.append(('univentionPolicyReference', self.oldpolicies, self.policies))

		return ml

	def _create(self):
		self.exceptions = []
		self._ldap_pre_create()
		self._update_policies()
		self.call_udm_property_hook('hook_ldap_pre_create', self)

		# Make sure all default values are set ...
		for name, p in self.descriptions.items():
			# ... if property has no option or any required option is currently enabled
			if self.has_key(name) and self.descriptions[name].default(self):
				self[name]  # __getitem__ sets default value

		# iterate over all properties and call checkLdap() of corresponding syntax
		self._call_checkLdap_on_all_property_syntaxes()

		al = self._ldap_addlist()
		al.extend(self._ldap_modlist())
		m = univention.admin.modules.get(self.module)

		# evaluate extended attributes
		ocs = set()
		for prop in getattr(m, 'extended_udm_attributes', []):
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simpleLdap._create: info[%s]:%r = %r' % (prop.name, self.has_key(prop.name), self.info.get(prop.name)))
			if prop.syntax == 'boolean' and self.info.get(prop.name) == '0':
				continue
			if self.has_key(prop.name) and self.info.get(prop.name):
				ocs.add(prop.objClass)

		# add object classes of (especially extended) options
		for option in self.options:
			try:
				opt = m.options[option]
			except KeyError:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, '%r does not specify option %r' % (m.module, option))
				continue
			ocs |= set(opt.objectClasses)

		# remove duplicated object classes
		for i in al:
			key, val = i[0], i[-1]  # might be a triple
			if val and key.lower() == 'objectclass':
				ocs -= set([val] if isinstance(val, basestring) else val)
		if ocs:
			al.append(('objectClass', list(ocs)))

		al = self.call_udm_property_hook('hook_ldap_addlist', self, al)

		# ensure univentionObject is set
		al.append(('objectClass', ['univentionObject', ]))
		al.append(('univentionObjectType', [self.module, ]))

		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "create object with dn: %s" % (self.dn,))
		univention.debug.debug(univention.debug.ADMIN, 99, 'Create dn=%r;\naddlist=%r;' % (self.dn, al))
		self.lo.add(self.dn, al)
		self._exists = True

		# if anything goes wrong we need to remove the already created object, otherwise we run into 'already exists' errors
		try:
			self._ldap_post_create()
		except:
			# ensure that there is no lock left
			import traceback
			import sys
			exc = sys.exc_info()
			univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, "Post-Create operation failed: %s" % (traceback.format_exc(),))
			try:
				self.cancel()
			except:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, "Post-create: cancel() failed: %s" % (traceback.format_exc(),))
			try:
				self.remove()
			except:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, "Post-create: remove() failed: %s" % (traceback.format_exc(),))
			raise exc[0], exc[1], exc[2]

		self.call_udm_property_hook('hook_ldap_post_create', self)

		self.save()
		return self.dn

	def _modify(self, modify_childs=1, ignore_license=0):
		self.exceptions = []

		self.__prevent_ad_property_change()

		self._ldap_pre_modify()
		self._update_policies()
		self.call_udm_property_hook('hook_ldap_pre_modify', self)

		# Make sure all default values are set...
		for name, p in self.descriptions.items():
			# ... if property has no option or any required option is currently enabled
			if self.has_key(name) and self.descriptions[name].default(self):
				self[name]  # __getitem__ sets default value

		# iterate over all properties and call checkLdap() of corresponding syntax
		self._call_checkLdap_on_all_property_syntaxes()

		ml = self._ldap_modlist()
		ml = self.call_udm_property_hook('hook_ldap_modlist', self, ml)
		ml = self._ldap_object_classes(ml)

		# FIXME: timeout without exception if objectClass of Object is not exsistant !!
		univention.debug.debug(univention.debug.ADMIN, 99, 'Modify dn=%r;\nmodlist=%r;\noldattr=%r;' % (self.dn, ml, self.oldattr))
		self.lo.modify(self.dn, ml, ignore_license=ignore_license)

		self._ldap_post_modify()
		self.call_udm_property_hook('hook_ldap_post_modify', self)

		self.save()
		return self.dn

	def _ldap_object_classes(self, ml):
		m = univention.admin.modules.get(self.module)

		def lowerset(vals):
			return set(x.lower() for x in vals)

		ocs = lowerset(_MergedAttributes(self, ml).get_attribute('objectClass'))
		unneeded_ocs = set()
		required_ocs = set()

		# evaluate (extended) options
		module_options = univention.admin.modules.options(self.module)
		available_options = set(module_options.keys())
		options = set(self.options)
		old_options = set(self.old_options)
		if options != old_options:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'options=%r; old_options=%r' % (options, old_options))
		unavailable_options = (options - available_options) | (old_options - available_options)
		if unavailable_options:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, '%r does not provide options: %r' % (self.module, unavailable_options))
		added_options = options - old_options - unavailable_options
		removed_options = old_options - options - unavailable_options

		# evaluate extended attributes
		for prop in getattr(m, 'extended_udm_attributes', []):
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simpleLdap._modify: extended attribute=%r  oc=%r' % (prop.name, prop.objClass))

			if self.has_key(prop.name) and self.info.get(prop.name) and (True if prop.syntax != 'boolean' else self.info.get(prop.name) != '0'):
				required_ocs |= set([prop.objClass])
				continue

			if prop.deleteObjClass:
				unneeded_ocs |= set([prop.objClass])

			# if the value is unset we need to remove the attribute completely
			if self.oldattr.get(prop.ldapMapping):
				ml = [x for x in ml if x[0].lower() != prop.ldapMapping.lower()]
				ml.append((prop.ldapMapping, self.oldattr.get(prop.ldapMapping), ''))

		unneeded_ocs |= reduce(set.union, (set(module_options[option].objectClasses) for option in removed_options), set())
		required_ocs |= reduce(set.union, (set(module_options[option].objectClasses) for option in added_options), set())

		ocs -= lowerset(unneeded_ocs)
		ocs |= lowerset(required_ocs)
		if lowerset(self.oldattr.get('objectClass', [])) == ocs:
			return ml

		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'OCS=%r; required=%r; removed: %r' % (ocs, required_ocs, unneeded_ocs))

		# case normalize object class names
		schema = self.lo.get_schema()
		ocs = set(schema.get_obj(ldap.schema.models.ObjectClass, x).names[0] for x in ocs)

		# make sure we still have a structural object class
		if not schema.get_structural_oc(ocs):
			structural_ocs = schema.get_structural_oc(unneeded_ocs)
			if not structural_ocs:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, 'missing structural object class. Modify will fail.')
				return ml
			univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'Preventing to remove last structural object class %r' % (structural_ocs,))
			ocs -= set(schema.get_obj(ldap.schema.models.ObjectClass, structural_ocs).names)

		# validate removal of object classes
		must, may = schema.attribute_types(ocs)
		allowed = set(name.lower() for attr in may.values() for name in attr.names) | set(name.lower() for attr in must.values() for name in attr.names)

		ml = [x for x in ml if x[0].lower() != 'objectclass']
		ml.append(('objectClass', self.oldattr.get('objectClass', []), list(ocs)))
		newattr = ldap.cidict.cidict(_MergedAttributes(self, ml).get_attributes())

		# make sure only attributes known by the object classes are set
		for attr, val in newattr.items():
			if not val:
				continue
			if re.sub(';binary$', '', attr.lower()) not in allowed:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'The attribute %r is not allowed by any object class.' % (attr,))
				# ml.append((attr, val, [])) # TODO: Remove the now invalid attribute instead
				return ml

		# require all MUST attributes to be set
		for attr in must.values():
			if not any(newattr.get(name) or newattr.get('%s;binary' % (name,)) for name in attr.names):
				univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'The attribute %r is required by the current object classes.' % (attr.names,))
				return ml

		ml = [x for x in ml if x[0].lower() != 'objectclass']
		ml.append(('objectClass', self.oldattr.get('objectClass', []), list(ocs)))

		return ml

	def _move_in_subordinates(self, olddn):
		result = self.lo.search(base=self.lo.base, filter=filter_format('(&(objectclass=person)(secretary=%s))', [olddn]), attr=['dn'])
		for subordinate, attr in result:
			self.lo.modify(subordinate, [('secretary', olddn, self.dn)])

	def _move_in_groups(self, olddn):
		for group in self.oldinfo.get('groups', []) + [self.oldinfo.get('machineAccountGroup', '')]:
			if group != '':
				members = self.lo.getAttr(group, 'uniqueMember')
				newmembers = []
				for member in members:
					if not member.lower() in (olddn.lower(), self.dn.lower(), ):
						newmembers.append(member)
				newmembers.append(self.dn)
				self.lo.modify(group, [('uniqueMember', members, newmembers)])

	def _move(self, newdn, modify_childs=1, ignore_license=0):
		self._ldap_pre_move(newdn)

		olddn = self.dn
		self.lo.rename(self.dn, newdn)
		self.dn = newdn

		try:
			self._move_in_groups(olddn)  # can be done always, will do nothing if oldinfo has no attribute 'groups'
			self._move_in_subordinates(olddn)
			self._ldap_post_move(olddn)
		except:
			# move back
			univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'simpleLdap._move: self._ldap_post_move failed, move object back to %s' % olddn)
			self.lo.rename(self.dn, olddn)
			self.dn = olddn
			raise

	def _remove(self, remove_childs=0):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'handlers/__init__._remove() called for %r with remove_childs=%r' % (self.dn, remove_childs))
		self.exceptions = []

		if _prevent_to_change_ad_properties and self._is_synced_object():
			raise univention.admin.uexceptions.invalidOperation(_('Objects from Active Directory can not be removed.'))

		self._ldap_pre_remove()
		self.call_udm_property_hook('hook_ldap_pre_remove', self)

		if remove_childs:
			subelements = []
			if 'FALSE' not in self.lo.getAttr(self.dn, 'hasSubordinates'):
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'handlers/__init__._remove() children of base dn %s' % (self.dn,))
				subelements = self.lo.search(base=self.dn, scope='one', attr=[])
			if subelements:
				try:
					for subolddn, suboldattrs in subelements:
						univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'remove: subelement %s' % subolddn)
						submodule = univention.admin.modules.identifyOne(subolddn, suboldattrs)
						submodule = univention.admin.modules.get(submodule)
						subobject = univention.admin.objects.get(submodule, None, self.lo, position='', dn=subolddn)
						subobject.remove(remove_childs)
				except:
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'remove: could not remove subelements')

		self.lo.delete(self.dn)
		self._exists = False

		self._ldap_post_remove()

		self.call_udm_property_hook('hook_ldap_post_remove', self)
		self.save()

	def loadPolicyObject(self, policy_type, reset=0):
		pathlist = []
		errors = 0
		pathResult = None

		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "loadPolicyObject: policy_type: %s" % policy_type)
		policy_module = univention.admin.modules.get(policy_type)

		# overwrite property descriptions
		univention.admin.ucr_overwrite_properties(policy_module, self.lo)
		# re-build layout if there any overwrites defined
		univention.admin.ucr_overwrite_module_layout(policy_module)

		# retrieve path info from 'cn=directory,cn=univention,<current domain>' object
		try:
			pathResult = self.lo.get('cn=directory,cn=univention,' + self.position.getDomain())
			if not pathResult:
				pathResult = self.lo.get('cn=default containers,cn=univention,' + self.position.getDomain())
		except:
			errors = 1
		infoattr = "univentionPolicyObject"
		if pathResult.has_key(infoattr) and pathResult[infoattr]:
			for i in pathResult[infoattr]:
				try:
					self.lo.searchDn(base=i, scope='base')
					pathlist.append(i)
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "loadPolicyObject: added path %s" % i)
				except Exception:
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "loadPolicyObject: invalid path setting: %s does not exist in LDAP" % i)
					continue  # looking for next policy container
				break  # at least one item has been found; so we can stop here since only pathlist[0] is used

		if not pathlist or errors:
			policy_position = self.position
		else:
			policy_position = univention.admin.uldap.position(self.position.getBase())
			policy_path = pathlist[0]
			try:
				prefix = univention.admin.modules.policyPositionDnPrefix(policy_module)
				self.lo.searchDn(base="%s,%s" % (prefix, policy_path), scope='base')
				policy_position.setDn("%s,%s" % (prefix, policy_path))
			except:
				policy_position.setDn(policy_path)

		for dn in self.policies:
			if univention.admin.modules.recognize(policy_module, dn, self.lo.get(dn)) and self.policyObjects.get(policy_type, None) and self.policyObjects[policy_type].cloned == dn and not reset:
				return self.policyObjects[policy_type]

		for dn in self.policies:
			modules = univention.admin.modules.identify(dn, self.lo.get(dn))
			for module in modules:
				if univention.admin.modules.name(module) == policy_type:
					self.policyObjects[policy_type] = univention.admin.objects.get(module, None, self.lo, policy_position, dn=dn)
					self.policyObjects[policy_type].clone(self)
					self._init_ldap_search(self.policyObjects[policy_type])

					return self.policyObjects[policy_type]
			if not modules:
				self.policies.remove(dn)

		if not self.policyObjects.get(policy_type, None) or reset:
			self.policyObjects[policy_type] = univention.admin.objects.get(policy_module, None, self.lo, policy_position)
			self.policyObjects[policy_type].copyIdentifier(self)
			self._init_ldap_search(self.policyObjects[policy_type])

		return self.policyObjects[policy_type]

	def _init_ldap_search(self, policy):
		properties = {}
		if hasattr(policy, 'property_descriptions'):
			properties = policy.property_descriptions
		elif hasattr(policy, 'descriptions'):
			properties = policy.descriptions
		for pname, prop in properties.items():
			if prop.syntax.name == 'LDAP_Search':
				prop.syntax._load(self.lo)
				if prop.syntax.viewonly:
					policy.mapping.unregister(pname)

	def _update_policies(self):
		_d = univention.debug.function('admin.handlers.simpleLdap._update_policies')
		for policy_type, policy_object in self.policyObjects.items():
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "simpleLdap._update_policies: processing policy of type: %s" % policy_type)
			if policy_object.changes:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "simpleLdap._update_policies: trying to create policy of type: %s" % policy_type)
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "simpleLdap._update_policies: policy_object.info=%s" % policy_object.info)
				policy_object.create()
				univention.admin.objects.replacePolicyReference(self, policy_type, policy_object.dn)

	def closePolicyObjects(self):
		self.policyObjects = {}

	def savePolicyObjects(self):
		self._update_policies()
		self.closePolicyObjects()

	def cancel(self):
		# method stub which is implemented by subclasses (see Bug #21070)
		pass

	def _call_checkLdap_on_all_property_syntaxes(self):
		""" calls checkLdap() method on every property if present.
			checkLdap() may rise an exception if the value does not match
			the constraints of the underlying syntax.
		"""
		properties = {}
		if hasattr(self, 'descriptions'):
			properties = self.descriptions
		for pname, prop in properties.items():
			if hasattr(prop.syntax, 'checkLdap'):
				prop.syntax.checkLdap(self.lo, self.info.get(pname))

	def __prevent_ad_property_change(self):
		if not _prevent_to_change_ad_properties or not self._is_synced_object():
			return

		for key in self.descriptions:
			if self.descriptions[key].readonly_when_synced:
				value = self.info.get(key)
				oldval = self.oldinfo.get(key)
				if oldval != value:
					raise univention.admin.uexceptions.valueMayNotChange(_('key=%(key)s old=%(old)s new=%(new)s') % {'key': key, 'old': oldval, 'new': value})

	def _is_synced_object(self):
		return 'synced' in self.oldattr.get('univentionObjectFlag', [])


class simpleComputer(simpleLdap):

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes=[]):
		simpleLdap.__init__(self, co, lo, position, dn, superordinate, attributes)

		self.newPrimaryGroupDn = 0
		self.oldPrimaryGroupDn = 0
		self.ip = []
		self.network_object = False
		self.old_network = 'None'
		self.__saved_dhcp_entry = None
		self.macRequest = 0
		self.ipRequest = 0
		# read-only attribute containing the FQDN of the host
		self.descriptions['fqdn'] = univention.admin.property(
			short_description='FQDN',
			long_description='',
			syntax=univention.admin.syntax.string,
			multivalue=False,
			options=[],
			required=False,
			may_change=False,
			identifies=False
		)
		self['dnsAlias'] = []  # defined here to avoid pseudo non-None value of [''] in modwizard search
		self.oldinfo['ip'] = []
		self.info['ip'] = []
		if self.exists():
			if 'aRecord' in self.oldattr:
				self.oldinfo['ip'].extend(self.oldattr['aRecord'])
				self.info['ip'].extend(self.oldattr['aRecord'])
			if 'aAAARecord' in self.oldattr:
				self.oldinfo['ip'].extend(map(lambda x: ipaddr.IPv6Address(x).exploded, self.oldattr['aAAARecord']))
				self.info['ip'].extend(map(lambda x: ipaddr.IPv6Address(x).exploded, self.oldattr['aAAARecord']))

	def getMachineSid(self, lo, position, uidNum, rid=None):
		# if rid is given, use it regardless of s4 connector
		if rid:
			searchResult = self.lo.search(filter='objectClass=sambaDomain', attr=['sambaSID'])
			domainsid = searchResult[0][1]['sambaSID'][0]
			sid = domainsid + '-' + rid
			univention.admin.allocators.request(self.lo, self.position, 'sid', sid)
			return sid
		else:
			# if no rid is given, create a domain sid or local sid if connector is present
			if self.s4connector_present:
				return 'S-1-4-%s' % uidNum
			else:
				num = uidNum
				machineSid = ""
				while not machineSid or machineSid == 'None':
					try:
						machineSid = univention.admin.allocators.requestUserSid(lo, position, num)
					except univention.admin.uexceptions.noLock:
						num = str(int(num) + 1)
				return machineSid

	# HELPER
	def __ip_from_ptr(self, zoneName, relativeDomainName):
		if 'ip6' in zoneName:
			return self.__ip_from_ptr_ipv6(zoneName, relativeDomainName)
		else:
			return self.__ip_from_ptr_ipv4(zoneName, relativeDomainName)

	def __ip_from_ptr_ipv4(self, zoneName, relativeDomainName):
		return '%s.%s' % (
			'.'.join(reversed(zoneName.replace('.in-addr.arpa', '').split('.'))),
			'.'.join(reversed(relativeDomainName.split('.'))))

	def __ip_from_ptr_ipv6(self, zoneName, relativeDomainName):
		fullName = relativeDomainName + '.' + zoneName.replace('.ip6.arpa', '')
		fullName = fullName.split('.')
		fullName = [''.join(reversed(fullName[i:i + 4])) for i in xrange(0, len(fullName), 4)]
		fullName.reverse()
		return ':'.join(fullName)

	def __is_ip(self, ip):
		# return True if valid IPv4 (0.0.0.0 is allowed) or IPv6 address
		try:
			ipaddr.IPAddress(ip)
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'IP[%s]? -> Yes' % ip)
			return True
		except ValueError:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'IP[%s]? -> No' % ip)
			return False

	def open(self):
		simpleLdap.open(self)

		self.newPrimaryGroupDn = 0
		self.oldPrimaryGroupDn = 0
		self.ip_alredy_requested = 0
		self.ip_freshly_set = False

		self.open_warning = None
		open_warnings = []

		self.__multiip = len(self['mac']) > 1 or len(self['ip']) > 1

		self['dnsEntryZoneForward'] = []
		self['dnsEntryZoneReverse'] = []
		self['dhcpEntryZone'] = []
		self['groups'] = []
		self['dnsEntryZoneAlias'] = []

		# search forward zone and insert into the object
		if self['name']:
			tmppos = univention.admin.uldap.position(self.position.getDomain())

			searchFilter = filter_format('(&(objectClass=dNSZone)(relativeDomainName=%s)(!(cNAMERecord=*)))', [self['name']])
			try:
				result = self.lo.search(base=tmppos.getBase(), scope='domain', filter=searchFilter, attr=['zoneName', 'aRecord', 'aAAARecord'], unique=False)

				zoneNames = []

				if result:
					for dn, attr in result:
						if 'aRecord' in attr:
							zoneNames.append((attr['zoneName'][0], attr['aRecord']))
						if 'aAAARecord' in attr:
							zoneNames.append((attr['zoneName'][0], map(lambda x: ipaddr.IPv6Address(x).exploded, attr['aAAARecord'])))

				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'zoneNames: %s' % zoneNames)

				if zoneNames:
					for zoneName in zoneNames:
						searchFilter = filter_format('(&(objectClass=dNSZone)(zoneName=%s)(relativeDomainName=@))', [zoneName[0]])

						try:
							results = self.lo.searchDn(base=tmppos.getBase(), scope='domain', filter=searchFilter, unique=False)
						except univention.admin.uexceptions.insufficientInformation, msg:
							raise univention.admin.uexceptions.insufficientInformation, msg

						univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'results: %s' % results)
						if results:
							for result in results:
								for ip in zoneName[1]:
									self['dnsEntryZoneForward'].append([result, ip])
							univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'dnsEntryZoneForward: %s' % str(self['dnsEntryZoneForward']))

			except univention.admin.uexceptions.insufficientInformation, msg:
				self['dnsEntryZoneForward'] = []
				raise univention.admin.uexceptions.insufficientInformation, msg

			if zoneNames:
				for zoneName in zoneNames:
					searchFilter = filter_format('(&(objectClass=dNSZone)(|(PTRRecord=%s)(PTRRecord=%s.%s.)))', (self['name'], self['name'], zoneName[0]))
					try:
						results = self.lo.search(base=tmppos.getBase(), scope='domain', attr=['relativeDomainName', 'zoneName'], filter=searchFilter, unique=False)
						for dn, attr in results:
							ip = self.__ip_from_ptr(attr['zoneName'][0], attr['relativeDomainName'][0])
							if not self.__is_ip(ip):
								univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'simpleComputer: dnsEntryZoneReverse: invalid IP address generated: %r' % (ip,))
								continue
							entry = [self.lo.parentDn(dn), ip]
							if entry not in self['dnsEntryZoneReverse']:
								self['dnsEntryZoneReverse'].append(entry)
					except univention.admin.uexceptions.insufficientInformation, msg:
						self['dnsEntryZoneReverse'] = []
						raise univention.admin.uexceptions.insufficientInformation, msg
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simpleComputer: dnsEntryZoneReverse: %s' % self['dnsEntryZoneReverse'])

			if zoneNames:
				for zoneName in zoneNames:
					searchFilter = filter_format('(&(objectClass=dNSZone)(|(cNAMERecord=%s)(cNAMERecord=%s.%s.)))', (self['name'], self['name'], zoneName[0]))
					try:
						results = self.lo.search(base=tmppos.getBase(), scope='domain', attr=['relativeDomainName', 'cNAMERecord', 'zoneName'], filter=searchFilter, unique=False)
						for dn, attr in results:
							dnsAlias = attr['relativeDomainName'][0]
							self['dnsAlias'].append(dnsAlias)
							dnsAliasZoneContainer = self.lo.parentDn(dn)
							if attr['cNAMERecord'][0] == self['name']:
								dnsForwardZone = attr['zoneName'][0]
							else:
								dnsForwardZone = zoneName[0]

							entry = [dnsForwardZone, dnsAliasZoneContainer, dnsAlias]
							if entry not in self['dnsEntryZoneAlias']:
								self['dnsEntryZoneAlias'].append(entry)
					except univention.admin.uexceptions.insufficientInformation, msg:
						self['dnsEntryZoneAlias'] = []
						raise univention.admin.uexceptions.insufficientInformation, msg
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simpleComputer: dnsEntryZoneAlias: %s' % self['dnsEntryZoneAlias'])

			if self['mac']:
				for macAddress in self['mac']:
					# mac address may be an empty string (Bug #21958)
					if not macAddress:
						continue

					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'open: DHCP; we have a mac address: %s' % macAddress)
					ethernet = 'ethernet ' + macAddress
					searchFilter = filter_format('(&(dhcpHWAddress=%s)(objectClass=univentionDhcpHost))', (ethernet,))
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'open: DHCP; we search for "%s"' % searchFilter)
					try:
						results = self.lo.search(base=tmppos.getBase(), scope='domain', attr=['univentionDhcpFixedAddress'], filter=searchFilter, unique=False)
						univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'open: DHCP; the result: "%s"' % results)
						for dn, attr in results:
							service = self.lo.parentDn(dn)
							if 'univentionDhcpFixedAddress' in attr:
								for ip in attr['univentionDhcpFixedAddress']:
									entry = (service, ip, macAddress)
									if entry not in self['dhcpEntryZone']:
										self['dhcpEntryZone'].append(entry)

							else:
								entry = (service, '', macAddress)
								if entry not in self['dhcpEntryZone']:
									self['dhcpEntryZone'].append(entry)
						univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'open: DHCP; self[ dhcpEntryZone ] = "%s"' % self['dhcpEntryZone'])

					except univention.admin.uexceptions.insufficientInformation, msg:
						raise univention.admin.uexceptions.insufficientInformation, msg

		if self.exists():
			if self.has_key('network'):
				self.old_network = self['network']

			# get groupmembership
			result = self.lo.search(base=self.lo.base, filter=filter_format('(&(objectclass=univentionGroup)(uniqueMember=%s))', [self.dn]), attr=['dn'])
			self['groups'] = [(x[0]) for x in result]

		if len(open_warnings) > 0:
			self.open_warning = ''
			for warn in open_warnings:
				self.open_warning += '\n' + warn

		if 'name' in self.info and 'domain' in self.info:
			self.info['fqdn'] = '%s.%s' % (self['name'], self['domain'])

	def __modify_dhcp_object(self, position, mac, ip=None):
		# identify the dhcp object with the mac address

		name = self['name']
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, '__modify_dhcp_object: position: "%s"; name: "%s"; mac: "%s"; ip: "%s"' % (position, name, mac, ip))
		if not all((name, mac)):
			return

		ethernet = 'ethernet %s' % mac

		tmppos = univention.admin.uldap.position(self.position.getDomain())
		if not position:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'could not access network object and given position is "None", using LDAP root as position for DHCP entry')
			position = tmppos.getBase()
		results = self.lo.search(base=position, scope='domain', attr=['univentionDhcpFixedAddress'], filter=filter_format('dhcpHWAddress=%s', [ethernet]), unique=False)

		if not results:
			# if the dhcp object doesn't exists, then we create it
			# but it is possible, that the hostname for the dhcp object is already used, so we use the _uv$NUM extension

			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'the dhcp object with the mac address "%s" does not exists, we create one' % ethernet)

			results = self.lo.searchDn(base=position, scope='domain', filter=filter_format('(&(objectClass=univentionDhcpHost)(|(cn=%s)(cn=%s_uv*)))', (name, name)), unique=False)
			if results:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'the host "%s" already has a dhcp object, so we search for the next free uv name' % (name))
				RE = re.compile(r'cn=[^,]+_uv(\d+),')
				taken = set(int(m.group(1)) for m in (RE.match(dn) for dn in results) if m)
				n = min(set(range(max(taken) + 1)) - taken) if taken else 0
				name = '%s_uv%d' % (name, n)

			dn = 'cn=%s,%s' % (escape_dn_chars(name), position)
			self.lo.add(dn, [
				('objectClass', ['top', 'univentionObject', 'univentionDhcpHost']),
				('univentionObjectType', ['dhcp/host']),
				('cn', [name]),
				('univentionDhcpFixedAddress', [ip]),
				('dhcpHWAddress', [ethernet]),
			])
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we just added the object "%s"' % (dn,))
		else:
			# if the object already exists, we append or remove the ip address
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'the dhcp object with the mac address "%s" exists, we change the ip' % ethernet)
			for dn, attr in results:
				if ip:
					if ip in attr.get('univentionDhcpFixedAddress', []):
						continue
					self.lo.modify(dn, [('univentionDhcpFixedAddress', '', ip)])
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we added the ip "%s"' % ip)
				else:
					self.lo.modify(dn, [('univentionDhcpFixedAddress', ip, '')])
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we removed the ip "%s"' % ip)

	def __rename_dns_object(self, position=None, old_name=None, new_name=None):
		for dns_line in self['dnsEntryZoneForward']:
			# dns_line may be the empty string
			if not dns_line:
				continue
			dn, ip = self.__split_dns_line(dns_line)
			if ':' in ip:  # IPv6
				results = self.lo.searchDn(base=dn, scope='domain', filter=filter_format('(&(relativeDomainName=%s)(aAAARecord=%s))', (old_name, ip)), unique=False)
			else:
				results = self.lo.searchDn(base=dn, scope='domain', filter=filter_format('(&(relativeDomainName=%s)(aRecord=%s))', (old_name, ip)), unique=False)
			for result in results:
				object = univention.admin.objects.get(univention.admin.modules.get('dns/host_record'), self.co, self.lo, position=self.position, dn=result)
				object.open()
				object['name'] = new_name
				object.modify()
		for dns_line in self['dnsEntryZoneReverse']:
			# dns_line may be the empty string
			if not dns_line:
				continue
			dn, ip = self.__split_dns_line(dns_line)
			results = self.lo.searchDn(base=dn, scope='domain', filter=filter_format('(|(pTRRecord=%s)(pTRRecord=%s.*))', (old_name, old_name)), unique=False)
			for result in results:
				object = univention.admin.objects.get(univention.admin.modules.get('dns/ptr_record'), self.co, self.lo, position=self.position, dn=result)
				object.open()
				object['ptr_record'] = [ptr_record.replace(old_name, new_name) for ptr_record in object.get('ptr_record', [])]
				object.modify()
		for entry in self['dnsEntryZoneAlias']:
			# entry may be the empty string
			if not entry:
				continue
			dnsforwardzone, dnsaliaszonecontainer, alias = entry
			results = self.lo.searchDn(base=dnsaliaszonecontainer, scope='domain', filter=filter_format('relativedomainname=%s', [alias]), unique=False)
			for result in results:
				object = univention.admin.objects.get(univention.admin.modules.get('dns/alias'), self.co, self.lo, position=self.position, dn=result)
				object.open()
				object['cname'] = '%s.%s.' % (new_name, dnsforwardzone)
				object.modify()

	def __rename_dhcp_object(self, old_name, new_name):
		module = univention.admin.modules.get('dhcp/host')
		tmppos = univention.admin.uldap.position(self.position.getDomain())
		for mac in self['mac']:
			# mac may be the empty string
			if not mac:
				continue
			ethernet = 'ethernet %s' % mac

			results = self.lo.searchDn(base=tmppos.getBase(), scope='domain', filter=filter_format('dhcpHWAddress=%s', [ethernet]), unique=False)
			if not results:
				continue
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simpleComputer: filter [ dhcpHWAddress = %s ]; results: %s' % (ethernet, results))

			for result in results:
				object = univention.admin.objects.get(module, self.co, self.lo, position=self.position, dn=result)
				object.open()
				object['host'] = object['host'].replace(old_name, new_name)
				object.modify()

	def __remove_from_dhcp_object(self, mac=None, ip=None):
		# if we got the mac address, then we remove the object
		# if we only got the ip address, we remove the ip address

		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we should remove a dhcp object: mac="%s", ip="%s"' % (mac, ip))

		dn = None

		tmppos = univention.admin.uldap.position(self.position.getDomain())
		if ip and mac:
			ethernet = 'ethernet %s' % mac
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we only remove the ip "%s" from the dhcp object' % ip)
			results = self.lo.search(base=tmppos.getBase(), scope='domain', attr=['univentionDhcpFixedAddress'], filter=filter_format('(&(dhcpHWAddress=%s)(univentionDhcpFixedAddress=%s))', (ethernet, ip)), unique=False)
			for dn, attr in results:
				object = univention.admin.objects.get(univention.admin.modules.get('dhcp/host'), self.co, self.lo, position=self.position, dn=dn)
				object.open()
				if ip in object['fixedaddress']:
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'fixedaddress: "%s"' % object['fixedaddress'])
					object['fixedaddress'].remove(ip)
					if len(object['fixedaddress']) == 0:
						object.remove()
					else:
						object.modify()
					dn = object.dn

		elif mac:
			ethernet = 'ethernet %s' % mac
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'Remove the following mac: ethernet: "%s"' % ethernet)
			results = self.lo.search(base=tmppos.getBase(), scope='domain', attr=['univentionDhcpFixedAddress'], filter=filter_format('dhcpHWAddress=%s', [ethernet]), unique=False)
			for dn, attr in results:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, '... done')
				object = univention.admin.objects.get(univention.admin.modules.get('dhcp/host'), self.co, self.lo, position=self.position, dn=dn)
				object.remove()
				dn = object.dn

		elif ip:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'Remove the following ip: "%s"' % ip)
			results = self.lo.search(base=tmppos.getBase(), scope='domain', attr=['univentionDhcpFixedAddress'], filter=filter_format('univentionDhcpFixedAddress=%s', [ip]), unique=False)
			for dn, attr in results:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, '... done')
				object = univention.admin.objects.get(univention.admin.modules.get('dhcp/host'), self.co, self.lo, position=self.position, dn=dn)
				object.remove()
				dn = object.dn

		return dn

	def __split_dhcp_line(self, entry):
		service = entry[0]
		ip = ''
		try:
			# sanitize mac address
			#   0011.2233.4455 -> 00:11:22:33:44:55 -> is guaranteed to work together with our DHCP server
			#   __split_dhcp_line may be used outside of UDM which means that MAC_Address.parse may not be called.
			mac = univention.admin.syntax.MAC_Address.parse(entry[-1])
			if self.__is_ip(entry[-2]):
				ip = entry[-2]
		except univention.admin.uexceptions.valueError:
			mac = ''
		return (service, ip, mac)

	def __split_dns_line(self, entry):
		zone = entry[0]
		if len(entry) > 1:
			ip = self.__is_ip(entry[1]) and entry[1] or None
		else:
			ip = None

		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'Split entry %s into zone %s and ip %s' % (entry, zone, ip))
		return (zone, ip)

	def __remove_dns_reverse_object(self, name, dnsEntryZoneReverse, ip):
		def modify(rdn, zoneDN):
			zone_name = zoneDN.split('=')[1].split(',')[0]
			for dn, attributes in self.lo.search(scope='domain', attr=['pTRRecord'], filter=filter_format('(&(relativeDomainName=%s)(zoneName=%s))', (rdn, zone_name))):
				if len(attributes['pTRRecord']) == 1:
					self.lo.delete('relativeDomainName=%s,%s' % (escape_dn_chars(rdn), zoneDN))
				else:
					for dn2, attributes2 in self.lo.search(scope='domain', attr=['zoneName'], filter=filter_format('(&(relativeDomainName=%s)(objectClass=dNSZone))', [name]), unique=False):
						self.lo.modify(dn, [('pTRRecord', '%s.%s.' % (name, attributes2['zoneName'][0]), '')])

				zone = univention.admin.handlers.dns.reverse_zone.object(self.co, self.lo, self.position, zoneDN)
				zone.open()
				zone.modify()

		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we should remove a dns reverse object: dnsEntryZoneReverse="%s", name="%s", ip="%s"' % (dnsEntryZoneReverse, name, ip))
		if dnsEntryZoneReverse:
			rdn = self.calc_dns_reverse_entry_name(ip, dnsEntryZoneReverse)
			if rdn:
				modify(rdn, dnsEntryZoneReverse)

		elif ip:
			tmppos = univention.admin.uldap.position(self.position.getDomain())
			results = self.lo.search(base=tmppos.getBase(), scope='domain', attr=['zoneDn'], filter=filter_format('(&(objectClass=dNSZone)(|(pTRRecord=%s)(pTRRecord=%s.*)))', (name, name)), unique=False)
			for dn, attr in results:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'DEBUG: dn: "%s"' % dn)
				zone = self.lo.parentDn(dn)
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'DEBUG: zone: "%s"' % zone)
				rdn = self.calc_dns_reverse_entry_name(ip, zone)
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'DEBUG: rdn: "%s"' % rdn)
				if rdn:
					try:
						modify(rdn, zone)
					except univention.admin.uexceptions.noObject:
						pass

	def __add_dns_reverse_object(self, name, zoneDn, ip):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we should create a dns reverse object: zoneDn="%s", name="%s", ip="%s"' % (zoneDn, name, ip))
		if name and zoneDn and ip:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'dns reverse object: start')
			hostname_list = []
			if ':' in ip:  # IPv6, e.g. ip=2001:db8:100::5
				# 0.1.8.b.d.0.1.0.0.2.ip6.arpa → 0.1.8.b.d.1.0.0.2 → ['0', '1', '8', 'b', 'd', '0', '1', '0', '0', '2', ]
				subnet = explode_dn(zoneDn, 1)[0].replace('.ip6.arpa', '').split('.')
				# ['0', '1', '8', 'b', 'd', '0', '1', '0', '0', '2', ] → ['2', '0', '0', '1', '0', 'd', 'b', '8', '1', '0', ]
				subnet.reverse()
				# ['2', '0', '0', '1', '0', 'd', 'b', '8', '1', '0', ] → ['2001', '0db8', '10', ] → '2001:0db8:10'
				subnet = ':'.join([''.join(subnet[i:i + 4]) for i in xrange(0, len(subnet), 4)])
				# '2001:db8:100:5' → '2001:0db8:0100:0000:0000:0000:0000:0005'
				ip = ipaddr.IPv6Address(ip).exploded
				if not ip.startswith(subnet):
					raise univention.admin.uexceptions.missingInformation, _('Reverse zone and IP address are incompatible.')
				# '2001:0db8:0100:0000:0000:0000:0000:0005' → '00:0000:0000:0000:0000:0005'
				ipPart = ip[len(subnet):]
				# '00:0000:0000:0000:0000:0005' → '0000000000000000000005' → ['0', '0', …, '0', '0', '5', ]
				pointer = list(ipPart.replace(':', ''))
				# ['0', '0', …, '0', '0', '5', ] → ['5', '0', '0', …, '0', '0', ]
				pointer.reverse()
				# ['5', '0', '0', …, '0', '0', ] → '5.0.0.….0.0'
				ipPart = '.'.join(pointer)
				tmppos = univention.admin.uldap.position(self.position.getDomain())
				# check in which forward zone the ip is set
				results = self.lo.search(base=tmppos.getBase(), scope='domain', attr=['zoneName'], filter=filter_format('(&(relativeDomainName=%s)(aAAARecord=%s))', (name, ip)), unique=False)
			else:
				subnet = '%s.' % ('.'.join(reversed(explode_dn(zoneDn, 1)[0].replace('.in-addr.arpa', '').split('.'))))
				ipPart = re.sub('^%s' % (re.escape(subnet),), '', ip)
				if ipPart == ip:
					raise univention.admin.uexceptions.InvalidDNS_Information, _('Reverse zone and IP address are incompatible.')
				ipPart = '.'.join(reversed(ipPart.split('.')))
				tmppos = univention.admin.uldap.position(self.position.getDomain())
				# check in which forward zone the ip is set
				results = self.lo.search(base=tmppos.getBase(), scope='domain', attr=['zoneName'], filter=filter_format('(&(relativeDomainName=%s)(aRecord=%s))', (name, ip)), unique=False)
			if results:
				for dn, attr in results:
					if 'zoneName' in attr:
						hostname = '%s.%s.' % (name, attr['zoneName'][0])
						if hostname not in hostname_list:
							hostname_list.append(hostname)

			if not hostname_list:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, 'Could not determine host record for name=%r, ip=%r. Not creating pointer record.' % (name, ip))
				return

			# check if the object exists
			results = self.lo.search(base=tmppos.getBase(), scope='domain', attr=['dn'], filter=filter_format('(&(relativeDomainName=%s)(%s=%s))', [ipPart] + list(ldap.dn.str2dn(zoneDn)[0][0][:2])), unique=False)
			if not results:
				self.lo.add('relativeDomainName=%s,%s' % (escape_dn_chars(ipPart), zoneDn), [
					('objectClass', ['top', 'dNSZone', 'univentionObject']),
					('univentionObjectType', ['dns/ptr_record']),
					('zoneName', [explode_dn(zoneDn, 1)[0]]),
					('relativeDomainName', [ipPart]),
					('PTRRecord', hostname_list)
				])

				# update Serial
				zone = univention.admin.handlers.dns.reverse_zone.object(self.co, self.lo, self.position, zoneDn)
				zone.open()
				zone.modify()

	def __remove_dns_forward_object(self, name, zoneDn, ip=None):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we should remove a dns forward object: zoneDn="%s", name="%s", ip="%s"' % (zoneDn, name, ip))
		if name:
			# check if dns forward object has more than one ip address
			if not ip:
				if zoneDn:
					self.lo.delete('relativeDomainName=%s,%s' % (escape_dn_chars(name), zoneDn))
					zone = univention.admin.handlers.dns.forward_zone.object(self.co, self.lo, self.position, zoneDn)
					zone.open()
					zone.modify()
			else:
				if zoneDn:
					base = zoneDn
				else:
					tmppos = univention.admin.uldap.position(self.position.getDomain())
					base = tmppos.getBase()
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'search base="%s"' % base)
				if ':' in ip:
					ip = ipaddr.IPv6Address(ip).exploded
					(attrEdit, attrOther, ) = ('aAAARecord', 'aRecord', )
				else:
					(attrEdit, attrOther, ) = ('aRecord', 'aAAARecord', )
				results = self.lo.search(base=base, scope='domain', attr=['aRecord', 'aAAARecord', ], filter=filter_format('(&(relativeDomainName=%s)(%s=%s))', (name, attrEdit, ip)), unique=False, required=False)
				for dn, attr in results:
					if attr[attrEdit] == [ip, ] and not attr.get(attrOther):  # the <ip> to be removed is the last on the object
						# remove the object
						self.lo.delete(dn)
						if not zoneDn:
							zone = self.lo.parentDn(dn)
						else:
							zone = zoneDn

						zone = univention.admin.handlers.dns.forward_zone.object(self.co, self.lo, self.position, zone)
						zone.open()
						zone.modify()
					else:
						# remove only the ip address attribute
						new_ip_list = copy.deepcopy(attr[attrEdit])
						new_ip_list.remove(ip)

						self.lo.modify(dn, [(attrEdit, attr[attrEdit], new_ip_list, ), ])

						if not zoneDn:
							zone = self.lo.parentDn(zoneDn)
						else:
							zone = zoneDn

						zone = univention.admin.handlers.dns.forward_zone.object(self.co, self.lo, self.position, zone)
						zone.open()
						zone.modify()

	def __add_related_ptrrecords(self, zoneDN, ip):
		if not all((zoneDN, ip)):
			return
		ptrrecord = '%s.%s.' % (self.info['name'], zoneDN.split('=')[1].split(',')[0])
		ip_split = ip.split('.')
		ip_split.reverse()
		search_filter = filter_format('(|(relativeDomainName=%s)(relativeDomainName=%s)(relativeDomainName=%s))', (ip_split[0], '.'.join(ip_split[:1]), '.'.join(ip_split[:2])))

		for dn, attributes in self.lo.search(base=zoneDN, scope='domain', attr=['pTRRecord'], filter=search_filter):
			self.lo.modify(dn, [('pTRRecord', '', ptrrecord)])

	def __remove_related_ptrrecords(self, zoneDN, ip):
		ptrrecord = '%s.%s.' % (self.info['name'], zoneDN.split('=')[1].split(',')[0])
		ip_split = ip.split('.')
		ip_split.reverse()
		search_filter = filter_format('(|(relativeDomainName=%s)(relativeDomainName=%s)(relativeDomainName=%s))', (ip_split[0], '.'.join(ip_split[:1]), '.'.join(ip_split[:2])))

		for dn, attributes in self.lo.search(base=zoneDN, scope='domain', attr=['pTRRecord'], filter=search_filter):
			if ptrrecord in attributes['pTRRecord']:
				self.lo.modify(dn, [('pTRRecord', ptrrecord, '')])

	def check_common_name_length(self):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'check_common_name_length with self["ip"] = %r and self["dnsEntryZoneForward"] = %r' % (self['ip'], self['dnsEntryZoneForward'], ))
		if len(self['ip']) > 0 and len(self['dnsEntryZoneForward']) > 0:
			for zone in self['dnsEntryZoneForward']:
				if zone == '':
					continue
				zoneName = univention.admin.uldap.explodeDn(zone[0], 1)[0]
				if len(zoneName) + len(self['name']) >= 63:
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simpleComputer: length of Common Name is too long: %d' % (len(zoneName) + len(self['name']) + 1))
					raise univention.admin.uexceptions.commonNameTooLong

	def __modify_dns_forward_object(self, name, zoneDn, new_ip, old_ip):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we should modify a dns forward object: zoneDn="%s", name="%s", new_ip="%s", old_ip="%s"' % (zoneDn, name, new_ip, old_ip))
		zone = None
		if old_ip and new_ip:
			if not zoneDn:
				tmppos = univention.admin.uldap.position(self.position.getDomain())
				base = tmppos.getBase()
			else:
				base = zoneDn
			if ':' in old_ip:  # IPv6
				old_ip = ipaddr.IPv6Address(old_ip).exploded
				results = self.lo.search(base=base, scope='domain', attr=['aAAARecord'], filter=filter_format('(&(relativeDomainName=%s)(aAAARecord=%s))', (name, old_ip)), unique=False)
			else:
				results = self.lo.search(base=base, scope='domain', attr=['aRecord'], filter=filter_format('(&(relativeDomainName=%s)(aRecord=%s))', (name, old_ip)), unique=False)
			for dn, attr in results:
				old_aRecord = attr.get('aRecord', [])
				new_aRecord = copy.deepcopy(attr.get('aRecord', []))
				old_aAAARecord = attr.get('aAAARecord', [])
				new_aAAARecord = copy.deepcopy(attr.get('aAAARecord', []))
				if ':' in old_ip:  # IPv6
					new_aAAARecord.remove(old_ip)
				else:
					new_aRecord.remove(old_ip)
				if ':' in new_ip:  # IPv6
					new_ip = ipaddr.IPv6Address(new_ip).exploded
					if new_ip not in new_aAAARecord:
						new_aAAARecord.append(new_ip)
				else:
					if new_ip not in new_aRecord:
						new_aRecord.append(new_ip)
				modlist = []
				if ':' in old_ip or ':' in new_ip:
					if old_aAAARecord != new_aAAARecord:
						modlist.append(('aAAARecord', old_aAAARecord, new_aAAARecord, ))
				if ':' not in old_ip or ':' not in new_ip:
					if old_aRecord != new_aRecord:
						modlist.append(('aRecord', old_aRecord, new_aRecord, ))
				self.lo.modify(dn, modlist)
				if not zoneDn:
					zone = self.lo.parentDn(dn)

			if zoneDn:
				zone = zoneDn

			if zone:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'update the zon sOARecord for the zone: %s' % zone)

				zone = univention.admin.handlers.dns.forward_zone.object(self.co, self.lo, self.position, zone)
				zone.open()
				zone.modify()

	def __add_dns_forward_object(self, name, zoneDn, ip):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we should add a dns forward object: zoneDn="%s", name="%s", ip="%s"' % (zoneDn, name, ip))
		if not all((name, ip, zoneDn)):
			return
		if ip.find(':') != -1:  # IPv6
			self.__add_dns_forward_object_ipv6(name, zoneDn, ipaddr.IPv6Address(ip).exploded)
		else:
			self.__add_dns_forward_object_ipv4(name, zoneDn, ip)

	def __add_dns_forward_object_ipv6(self, name, zoneDn, ip):
			ip = ipaddr.IPv6Address(ip).exploded
			results = self.lo.search(base=zoneDn, scope='domain', attr=['aAAARecord'], filter=filter_format('(&(relativeDomainName=%s)(!(cNAMERecord=*)))', (name,)), unique=False)
			if not results:
				try:
					self.lo.add('relativeDomainName=%s,%s' % (escape_dn_chars(name), zoneDn), [
						('objectClass', ['top', 'dNSZone', 'univentionObject']),
						('univentionObjectType', ['dns/host_record']),
						('zoneName', univention.admin.uldap.explodeDn(zoneDn, 1)[0]),
						('aAAARecord', [ip]),
						('relativeDomainName', [name])
					])
				except univention.admin.uexceptions.objectExists, dn:
					raise univention.admin.uexceptions.dnsAliasRecordExists, dn
				# TODO: check if zoneDn really a forwardZone, maybe it is a container under a zone
				zone = univention.admin.handlers.dns.forward_zone.object(self.co, self.lo, self.position, zoneDn)
				zone.open()
				zone.modify()
			else:
				for dn, attr in results:
					if 'aAAARecord' in attr:
						new_ip_list = copy.deepcopy(attr['aAAARecord'])
						if ip not in new_ip_list:
							new_ip_list.append(ip)
							self.lo.modify(dn, [('aAAARecord', attr['aAAARecord'], new_ip_list)])
					else:
						self.lo.modify(dn, [('aAAARecord', '', ip)])

	def __add_dns_forward_object_ipv4(self, name, zoneDn, ip):
			results = self.lo.search(base=zoneDn, scope='domain', attr=['aRecord'], filter=filter_format('(&(relativeDomainName=%s)(!(cNAMERecord=*)))', (name,)), unique=False)
			if not results:
				try:
					self.lo.add('relativeDomainName=%s,%s' % (escape_dn_chars(name), zoneDn), [
						('objectClass', ['top', 'dNSZone', 'univentionObject']),
						('univentionObjectType', ['dns/host_record']),
						('zoneName', univention.admin.uldap.explodeDn(zoneDn, 1)[0]),
						('ARecord', [ip]),
						('relativeDomainName', [name])
					])
				except univention.admin.uexceptions.objectExists, dn:
					raise univention.admin.uexceptions.dnsAliasRecordExists, dn
				# TODO: check if zoneDn really a forwardZone, maybe it is a container under a zone
				zone = univention.admin.handlers.dns.forward_zone.object(self.co, self.lo, self.position, zoneDn)
				zone.open()
				zone.modify()
			else:
				for dn, attr in results:
					if 'aRecord' in attr:
						new_ip_list = copy.deepcopy(attr['aRecord'])
						if ip not in new_ip_list:
							new_ip_list.append(ip)
							self.lo.modify(dn, [('aRecord', attr['aRecord'], new_ip_list)])
					else:
						self.lo.modify(dn, [('aRecord', '', ip)])

	def __add_dns_alias_object(self, name, dnsForwardZone, dnsAliasZoneContainer, alias):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'add a dns alias object: name="%s", dnsForwardZone="%s", dnsAliasZoneContainer="%s", alias="%s"' % (name, dnsForwardZone, dnsAliasZoneContainer, alias))
		alias = alias.rstrip('.')
		if name and dnsForwardZone and dnsAliasZoneContainer and alias:
			results = self.lo.search(base=dnsAliasZoneContainer, scope='domain', attr=['cNAMERecord'], filter=filter_format('relativeDomainName=%s', (alias,)), unique=False)
			if not results:
				self.lo.add('relativeDomainName=%s,%s' % (escape_dn_chars(alias), dnsAliasZoneContainer), [
					('objectClass', ['top', 'dNSZone', 'univentionObject']),
					('univentionObjectType', ['dns/alias']),
					('zoneName', univention.admin.uldap.explodeDn(dnsAliasZoneContainer, 1)[0]),
					('cNAMERecord', ["%s.%s." % (name, dnsForwardZone)]),
					('relativeDomainName', [alias])
				])

				# TODO: check if dnsAliasZoneContainer really is a forwardZone, maybe it is a container under a zone
				zone = univention.admin.handlers.dns.forward_zone.object(self.co, self.lo, self.position, dnsAliasZoneContainer)
				zone.open()
				zone.modify()
			else:
				# thow exeption, cNAMERecord is single value
				raise univention.admin.uexceptions.dnsAliasAlreadyUsed, _('DNS alias is already in use.')

	def __remove_dns_alias_object(self, name, dnsForwardZone, dnsAliasZoneContainer, alias=None):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'remove a dns alias object: name="%s", dnsForwardZone="%s", dnsAliasZoneContainer="%s", alias="%s"' % (name, dnsForwardZone, dnsAliasZoneContainer, alias))
		if name:
			if alias:
				if dnsAliasZoneContainer:
					self.lo.delete('relativeDomainName=%s,%s' % (escape_dn_chars(alias), dnsAliasZoneContainer))
					zone = univention.admin.handlers.dns.forward_zone.object(self.co, self.lo, self.position, dnsAliasZoneContainer)
					zone.open()
					zone.modify()
				elif dnsForwardZone:
					tmppos = univention.admin.uldap.position(self.position.getDomain())
					base = tmppos.getBase()
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'search base="%s"' % base)
					results = self.lo.search(base=base, scope='domain', attr=['zoneName'], filter=filter_format('(&(objectClass=dNSZone)(relativeDomainName=%s)(cNAMERecord=%s.%s.))', (alias, name, dnsForwardZone)), unique=False, required=False)
					for dn, attr in results:
						# remove the object
						self.lo.delete(dn)
						# and update the SOA version number for the zone
						results = self.lo.searchDn(base=tmppos.getBase(), scope='domain', filter=filter_format('(&(objectClass=dNSZone)(zoneName=%s)(relativeDomainName=@))', (attr['zoneName'][0],)), unique=False)
						for zoneDn in results:
							zone = univention.admin.handlers.dns.forward_zone.object(self.co, self.lo, self.position, zoneDn)
							zone.open()
							zone.modify()
					else:
						# could thow some exeption
						pass
			else:
				if dnsForwardZone:
					tmppos = univention.admin.uldap.position(self.position.getDomain())
					base = tmppos.getBase()
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'search base="%s"' % base)
					results = self.lo.search(base=base, scope='domain', attr=['zoneName'], filter=filter_format('(&(objectClass=dNSZone)(&(cNAMERecord=%s)(cNAMERecord=%s.%s.))', (name, name, dnsForwardZone)), unique=False, required=False)
					for dn, attr in results:
						# remove the object
						self.lo.delete(dn)
						# and update the SOA version number for the zone
						results = self.lo.searchDn(base=tmppos.getBase(), scope='domain', filter=filter_format('(&(objectClass=dNSZone)(zoneName=%s)(relativeDomainName=@))', (attr['zoneName'][0],)), unique=False)
						for zoneDn in results:
							zone = univention.admin.handlers.dns.forward_zone.object(self.co, self.lo, self.position, zoneDn)
							zone.open()
							zone.modify()
				else:  # not enough info to remove alias entries
					pass

	def _ldap_post_modify(self):

		self.__multiip |= len(self['mac']) > 1 or len(self['ip']) > 1

		for entry in self.__changes['dhcpEntryZone']['remove']:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simpleComputer: dhcp check: removed: %s' % (entry,))
			dn, ip, mac = self.__split_dhcp_line(entry)
			if not ip and not mac and not self.__multiip:
				mac = ''
				if self['mac']:
					mac = self['mac'][0]
				self.__remove_from_dhcp_object(mac=mac)
			else:
				self.__remove_from_dhcp_object(ip=ip, mac=mac)

		for entry in self.__changes['dhcpEntryZone']['add']:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simpleComputer: dhcp check: added: %s' % (entry,))
			dn, ip, mac = self.__split_dhcp_line(entry)
			if not ip and not mac and not self.__multiip:
				ip, mac = ('', '')
				if self['ip']:
					ip = self['ip'][0]
				if self['mac']:
					mac = self['mac'][0]
			self.__modify_dhcp_object(dn, mac, ip=ip)

		for entry in self.__changes['dnsEntryZoneForward']['remove']:
			dn, ip = self.__split_dns_line(entry)
			if not ip and not self.__multiip:
				ip = ''
				if self['ip']:
					ip = self['ip'][0]
				self.__remove_dns_forward_object(self['name'], dn, ip)
				self.__remove_related_ptrrecords(dn, ip)
			else:
				self.__remove_dns_forward_object(self['name'], dn, ip)
				self.__remove_related_ptrrecords(dn, ip)

		for entry in self.__changes['dnsEntryZoneForward']['add']:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we should add a dns forward object "%s"' % (entry,))
			dn, ip = self.__split_dns_line(entry)
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'changed the object to dn="%s" and ip="%s"' % (dn, ip))
			if not ip and not self.__multiip:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'no multiip environment')
				ip = ''
				if self['ip']:
					ip = self['ip'][0]
				self.__add_dns_forward_object(self['name'], dn, ip)
				self.__add_related_ptrrecords(dn, ip)
			else:
				self.__add_dns_forward_object(self['name'], dn, ip)
				self.__add_related_ptrrecords(dn, ip)

		for entry in self.__changes['dnsEntryZoneReverse']['remove']:
			dn, ip = self.__split_dns_line(entry)
			if not ip and not self.__multiip:
				ip = ''
				if self['ip']:
					ip = self['ip'][0]
				self.__remove_dns_reverse_object(self['name'], dn, ip)
			else:
				self.__remove_dns_reverse_object(self['name'], dn, ip)

		for entry in self.__changes['dnsEntryZoneReverse']['add']:
			dn, ip = self.__split_dns_line(entry)
			if not ip and not self.__multiip:
				ip = ''
				if self['ip']:
					ip = self['ip'][0]
				self.__add_dns_reverse_object(self['name'], dn, ip)
			else:
				self.__add_dns_reverse_object(self['name'], dn, ip)

		for entry in self.__changes['dnsEntryZoneAlias']['remove']:
			dnsForwardZone, dnsAliasZoneContainer, alias = entry
			if not alias:
				# nonfunctional code since self[ 'alias' ] should be self[ 'dnsAlias' ], but ths case does not seem to occur
				self.__remove_dns_alias_object(self['name'], dnsForwardZone, dnsAliasZoneContainer, self['alias'][0])
			else:
				self.__remove_dns_alias_object(self['name'], dnsForwardZone, dnsAliasZoneContainer, alias)

		for entry in self.__changes['dnsEntryZoneAlias']['add']:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we should add a dns alias object "%s"' % (entry,))
			dnsForwardZone, dnsAliasZoneContainer, alias = entry
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'changed the object to dnsForwardZone [%s], dnsAliasZoneContainer [%s] and alias [%s]' % (dnsForwardZone, dnsAliasZoneContainer, alias))
			if not alias:
				self.__add_dns_alias_object(self['name'], dnsForwardZone, dnsAliasZoneContainer, self['alias'][0])
			else:
				self.__add_dns_alias_object(self['name'], dnsForwardZone, dnsAliasZoneContainer, alias)

		for entry in self.__changes['mac']['remove']:
			self.__remove_from_dhcp_object(mac=entry)

		changed_ip = False
		for entry in self.__changes['ip']['remove']:
			# self.__remove_from_dhcp_object(ip=entry)
			if not self.__multiip:
				if len(self.__changes['ip']['add']) > 0:
					# we change
					single_ip = self.__changes['ip']['add'][0]
					self.__modify_dns_forward_object(self['name'], None, single_ip, entry)
					changed_ip = True
					for mac in self['mac']:
						dn = self.__remove_from_dhcp_object(ip=entry, mac=mac)
						try:
							dn = self.lo.parentDn(dn)
							self.__modify_dhcp_object(dn, mac, ip=single_ip)
						except:
							pass
				else:
					# remove the dns objects
					self.__remove_dns_forward_object(self['name'], None, entry)
			else:
				self.__remove_dns_forward_object(self['name'], None, entry)
				self.__remove_from_dhcp_object(ip=entry)

			self.__remove_dns_reverse_object(self['name'], None, entry)

		for entry in self.__changes['ip']['add']:
			if not self.__multiip:
				if self.get('dnsEntryZoneForward', []) and not changed_ip:
					self.__add_dns_forward_object(self['name'], self['dnsEntryZoneForward'][0][0], entry)
				for dnsEntryZoneReverse in self.get('dnsEntryZoneReverse', []):
					x, ip = self.__split_dns_line(dnsEntryZoneReverse)
					zoneIsV6 = explode_dn(x, 1)[0].endswith('.ip6.arpa')
					entryIsV6 = ':' in entry
					if zoneIsV6 == entryIsV6:
						self.__add_dns_reverse_object(self['name'], x, entry)

		if self.__changes['name']:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simpleComputer: name has changed')
			self.__update_groups_after_namechange()
			self.__rename_dhcp_object(old_name=self.__changes['name'][0], new_name=self.__changes['name'][1])
			self.__rename_dns_object(position=None, old_name=self.__changes['name'][0], new_name=self.__changes['name'][1])

		if self.ipRequest == 1 and self['ip']:
			for ipAddress in self['ip']:
				if ipAddress:
					univention.admin.allocators.confirm(self.lo, self.position, 'aRecord', ipAddress)
			self.ipRequest = 0

		if self.macRequest == 1 and self['mac']:
			for macAddress in self['mac']:
				if macAddress:
					univention.admin.allocators.confirm(self.lo, self.position, 'mac', macAddress)
			self.macRequest = 0

		self.update_groups()

	def __remove_associated_domain(self, entry):
		dn, ip = self.__split_dns_line(entry)
		domain = explode_rdn(dn, 1)[0]
		if self.info.get('domain', None) == domain:
			self.info['domain'] = None

	def __set_associated_domain(self, entry):
		dn, ip = self.__split_dns_line(entry)
		domain = explode_rdn(dn, 1)[0]
		if not self.info.get('domain', None):
			self.info['domain'] = domain

	def _ldap_modlist(self):
		self.__changes = {
			'mac': {'remove': [], 'add': []},
			'ip': {'remove': [], 'add': []},
			'name': None,
			'dnsEntryZoneForward': {'remove': [], 'add': []},
			'dnsEntryZoneReverse': {'remove': [], 'add': []},
			'dnsEntryZoneAlias': {'remove': [], 'add': []},
			'dhcpEntryZone': {'remove': [], 'add': []}
		}
		ml = []
		if self.hasChanged('mac'):
			for macAddress in self.info.get('mac', []):
				if macAddress in self.oldinfo.get('mac', []):
					continue
				try:
					mac = univention.admin.allocators.request(self.lo, self.position, 'mac', value=macAddress)
					if not mac:
						self.cancel()
						raise univention.admin.uexceptions.noLock
					self.alloc.append(('mac', macAddress))
					self.__changes['mac']['add'].append(macAddress)
				except univention.admin.uexceptions.noLock:
					self.cancel()
					univention.admin.allocators.release(self.lo, self.position, "mac", macAddress)
					raise univention.admin.uexceptions.macAlreadyUsed, ' %s' % macAddress
				self.macRequest = 1
			for macAddress in self.oldinfo.get('mac', []):
				if macAddress in self.info.get('mac', []):
					continue
				self.__changes['mac']['remove'].append(macAddress)

		oldAddresses = self.oldinfo.get('ip')
		newAddresses = self.info.get('ip')
		oldARecord = []
		newARecord = []
		oldAaaaRecord = []
		newAaaaRecord = []
		if oldAddresses != newAddresses:
			if oldAddresses:
				for address in oldAddresses:
					if ':' in address:  # IPv6
						oldAaaaRecord.append(address)
					else:
						oldARecord.append(address)
			if newAddresses:
				for address in newAddresses:
					if ':' in address:  # IPv6
						newAaaaRecord.append(ipaddr.IPv6Address(address).exploded)
					else:
						newARecord.append(address)
			ml.append(('aRecord', oldARecord, newARecord, ))
			ml.append(('aAAARecord', oldAaaaRecord, newAaaaRecord, ))

		if self.hasChanged('ip'):
			for ipAddress in self['ip']:
				if not ipAddress:
					continue
				if ipAddress in self.oldinfo.get('ip'):
					continue
				if not self.ip_alredy_requested:
					try:
						IpAddr = univention.admin.allocators.request(self.lo, self.position, 'aRecord', value=ipAddress)
						if not IpAddr:
							self.cancel()
							raise univention.admin.uexceptions.noLock
						self.alloc.append(('aRecord', ipAddress))
					except univention.admin.uexceptions.noLock:
						self.cancel()
						univention.admin.allocators.release(self.lo, self.position, "aRecord", ipAddress)
						self.ip_alredy_requested = 0
						raise univention.admin.uexceptions.ipAlreadyUsed, ' %s' % ipAddress
				else:
					IpAddr = ipAddress

				self.alloc.append(('aRecord', IpAddr))

				self.ipRequest = 1
				self.__changes['ip']['add'].append(ipAddress)

			for ipAddress in self.oldinfo.get('ip', []):
				if ipAddress in self.info['ip']:
					continue
				self.__changes['ip']['remove'].append(ipAddress)

		if self.hasChanged('name'):
			ml.append(('sn', self.oldattr.get('sn', [None])[0], self['name']))
			self.__changes['name'] = (self.oldattr.get('sn', [None])[0], self['name'])

		if self.hasChanged('ip') or self.hasChanged('mac'):
			dhcp = [self.__split_dhcp_line(entry) for entry in self.info.get('dhcpEntryZone', [])]
			if len(newAddresses) <= 1 and len(self.info.get('mac', [])) == 1 and dhcp:
				# In this special case, we assume the mapping between ip/mac address to be
				# unique. The dhcp entry needs to contain the mac address (as specified by
				# the ldap search for dhcp entries), the ip address may not correspond to
				# the ip address associated with the computer ldap object, but this would
				# be erroneous anyway. We therefore update the dhcp entry to correspond to
				# the current ip and mac address. (Bug #20315)
				self.info['dhcpEntryZone'] = [
					(dn, newAddresses[0] if newAddresses else '', self.info['mac'][0])
					for (dn, ip, mac) in dhcp
				]
			else:
				# in all other cases, we remove old dhcp entries that do not match ip or
				# mac addresses (Bug #18966)
				removedIPs = set(self.oldinfo.get('ip', [])) - set(self['ip'])
				removedMACs = set(self.oldinfo.get('mac', [])) - set(self['mac'])
				self.info['dhcpEntryZone'] = [
					(dn, ip, mac)
					for (dn, ip, mac) in dhcp
					if not (ip in removedIPs or mac in removedMACs)
				]

		if self.hasChanged('dhcpEntryZone'):
			if 'dhcpEntryZone' in self.oldinfo:
				if 'dhcpEntryZone' in self.info:
					for entry in self.oldinfo['dhcpEntryZone']:
						if entry not in self.info['dhcpEntryZone']:
							self.__changes['dhcpEntryZone']['remove'].append(entry)
				else:
					for entry in self.oldinfo['dhcpEntryZone']:
						self.__changes['dhcpEntryZone']['remove'].append(entry)
			if 'dhcpEntryZone' in self.info:
				for entry in self.info['dhcpEntryZone']:
					# check if line is valid
					dn, ip, mac = self.__split_dhcp_line(entry)
					if dn and mac:
						if entry not in self.oldinfo.get('dhcpEntryZone', []):
							self.__changes['dhcpEntryZone']['add'].append(entry)
					else:
						raise univention.admin.uexceptions.invalidDhcpEntry, _('The DHCP entry for this host should contain the zone LDAP-DN, the IP address and the MAC address.')

		if self.hasChanged('dnsEntryZoneForward'):
			for entry in self.oldinfo.get('dnsEntryZoneForward', []):
				if entry not in self.info.get('dnsEntryZoneForward', []):
					self.__changes['dnsEntryZoneForward']['remove'].append(entry)
					self.__remove_associated_domain(entry)
			for entry in self.info.get('dnsEntryZoneForward', []):
				if entry == '':
					continue
				if entry not in self.oldinfo.get('dnsEntryZoneForward', []):
					self.__changes['dnsEntryZoneForward']['add'].append(entry)
				self.__set_associated_domain(entry)

		if self.hasChanged('dnsEntryZoneReverse'):
			for entry in self.oldinfo.get('dnsEntryZoneReverse', []):
				if entry not in self.info.get('dnsEntryZoneReverse', []):
					self.__changes['dnsEntryZoneReverse']['remove'].append(entry)
			for entry in self.info.get('dnsEntryZoneReverse', []):
				if entry not in self.oldinfo.get('dnsEntryZoneReverse', []):
					self.__changes['dnsEntryZoneReverse']['add'].append(entry)

		if self.hasChanged('dnsEntryZoneAlias'):
			for entry in self.oldinfo.get('dnsEntryZoneAlias', []):
				if entry not in self.info.get('dnsEntryZoneAlias', []):
					self.__changes['dnsEntryZoneAlias']['remove'].append(entry)
			for entry in self.info.get('dnsEntryZoneAlias', []):
				# check if line is valid
				dnsForwardZone, dnsAliasZoneContainer, alias = entry
				if dnsForwardZone and dnsAliasZoneContainer and alias:
					if entry not in self.oldinfo.get('dnsEntryZoneAlias', []):
						self.__changes['dnsEntryZoneAlias']['add'].append(entry)
				else:
					raise univention.admin.uexceptions.invalidDNSAliasEntry, _('The DNS alias entry for this host should contain the zone name, the alias zone container LDAP-DN and the alias.')

		self.__multiip = len(self['mac']) > 1 or len(self['ip']) > 1

		ml += super(simpleComputer, self)._ldap_modlist()

		return ml

	@classmethod
	def calc_dns_reverse_entry_name(cls, sip, reverseDN):
		"""
		>>> simpleComputer.calc_dns_reverse_entry_name('10.200.2.5', 'subnet=2.200.10.in-addr.arpa')
		'5'
		>>> simpleComputer.calc_dns_reverse_entry_name('10.200.2.5', 'subnet=200.10.in-addr.arpa')
		'5.2'
		>>> simpleComputer.calc_dns_reverse_entry_name('2001:db8::3', 'subnet=0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa')
		'3.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0'
		"""
		if ':' in sip:
			subnet = explode_dn(reverseDN, 1)[0].replace('.ip6.arpa', '').split('.')
			ip = list(ipaddr.IPv6Address(sip).exploded.replace(':', ''))
			return cls.calc_dns_reverse_entry_name_do(32, subnet, ip)
		else:
			subnet = explode_dn(reverseDN, 1)[0].replace('.in-addr.arpa', '').split('.')
			ip = sip.split('.')
			return cls.calc_dns_reverse_entry_name_do(4, subnet, ip)

	@staticmethod
	def calc_dns_reverse_entry_name_do(maxLength, zoneNet, ip):
		"""
		>>> simpleComputer.calc_dns_reverse_entry_name_do(3, ['2','1'], ['1','2','3'])
		'3'
		>>> simpleComputer.calc_dns_reverse_entry_name_do(3, ['1'], ['1','2','3'])
		'3.2'
		>>> simpleComputer.calc_dns_reverse_entry_name_do(4, ['0'], ['1','2','3'])
		0
		"""
		zoneNet.reverse()
		if not ip[:len(zoneNet)] == zoneNet:
			return 0
		ip.reverse()
		return '.'.join(ip[: maxLength - len(zoneNet)])

	def _ldap_pre_create(self):
		super(simpleComputer, self)._ldap_pre_create()
		self.check_common_name_length()

	def _ldap_pre_modify(self):
		self.check_common_name_length()

	def _ldap_post_create(self):
		for entry in self.__changes['dhcpEntryZone']['remove']:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simpleComputer: dhcp check: removed: %s' % (entry,))
			dn, ip, mac = self.__split_dhcp_line(entry)
			if not ip and not mac and not self.__multiip:
				mac = ''
				if self['mac']:
					mac = self['mac'][0]
				self.__remove_from_dhcp_object(mac=mac)
			else:
				self.__remove_from_dhcp_object(ip=ip, mac=mac)

		for entry in self.__changes['dhcpEntryZone']['add']:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simpleComputer: dhcp check: added: %s' % (entry,))
			dn, ip, mac = self.__split_dhcp_line(entry)
			if not ip and not mac and not self.__multiip:
				if len(self['ip']) > 0 and len(self['mac']) > 0:
					self.__modify_dhcp_object(dn, self['mac'][0], ip=self['ip'][0])
			else:
				self.__modify_dhcp_object(dn, mac, ip=ip)

		for entry in self.__changes['dnsEntryZoneForward']['remove']:
			dn, ip = self.__split_dns_line(entry)
			if not ip and not self.__multiip:
				ip = ''
				if self['ip']:
					ip = self['ip'][0]
				self.__remove_dns_forward_object(self['name'], dn, ip)
			else:
				self.__remove_dns_forward_object(self['name'], dn, ip)

		for entry in self.__changes['dnsEntryZoneForward']['add']:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we should add a dns forward object "%s"' % (entry,))
			dn, ip = self.__split_dns_line(entry)
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'changed the object to dn="%s" and ip="%s"' % (dn, ip))
			if not ip and not self.__multiip:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'no multiip environment')
				ip = ''
				if self['ip']:
					ip = self['ip'][0]
				self.__add_dns_forward_object(self['name'], dn, ip)
			else:
				self.__add_dns_forward_object(self['name'], dn, ip)

		for entry in self.__changes['dnsEntryZoneReverse']['remove']:
			dn, ip = self.__split_dns_line(entry)
			if not ip and not self.__multiip:
				ip = ''
				if self['ip']:
					ip = self['ip'][0]
				self.__remove_dns_reverse_object(self['name'], dn, ip)
			else:
				self.__remove_dns_reverse_object(self['name'], dn, ip)

		for entry in self.__changes['dnsEntryZoneReverse']['add']:
			dn, ip = self.__split_dns_line(entry)
			if not ip and not self.__multiip:
				ip = ''
				if self['ip']:
					ip = self['ip'][0]
				self.__add_dns_reverse_object(self['name'], dn, ip)
			else:
				self.__add_dns_reverse_object(self['name'], dn, ip)

		if not self.__multiip:
			if len(self.get('dhcpEntryZone', [])) > 0:
				dn, ip, mac = self['dhcpEntryZone'][0]
				for entry in self.__changes['mac']['add']:
					if len(self['ip']) > 0:
						self.__modify_dhcp_object(dn, entry, ip=self['ip'][0])
					else:
						self.__modify_dhcp_object(dn, entry)
				for entry in self.__changes['ip']['add']:
					if len(self['mac']) > 0:
						self.__modify_dhcp_object(dn, self['mac'][0], ip=entry)

		for entry in self.__changes['dnsEntryZoneAlias']['remove']:
			dnsForwardZone, dnsAliasZoneContainer, alias = entry
			if not alias:
				# nonfunctional code since self[ 'alias' ] should be self[ 'dnsAlias' ], but this case does not seem to occur
				self.__remove_dns_alias_object(self['name'], dnsForwardZone, dnsAliasZoneContainer, self['alias'][0])
			else:
				self.__remove_dns_alias_object(self['name'], dnsForwardZone, dnsAliasZoneContainer, alias)
		for entry in self.__changes['dnsEntryZoneAlias']['add']:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'we should add a dns alias object "%s"' % (entry,))
			dnsForwardZone, dnsAliasZoneContainer, alias = entry
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'changed the object to dnsForwardZone [%s], dnsAliasZoneContainer [%s] and alias [%s]' % (dnsForwardZone, dnsAliasZoneContainer, alias))
			if not alias:
				self.__add_dns_alias_object(self['name'], dnsForwardZone, dnsAliasZoneContainer, self['alias'][0])
			else:
				self.__add_dns_alias_object(self['name'], dnsForwardZone, dnsAliasZoneContainer, alias)

		if self.ipRequest == 1 and self['ip']:
			for ipAddress in self['ip']:
				if ipAddress:
					univention.admin.allocators.confirm(self.lo, self.position, 'aRecord', ipAddress)
			self.ipRequest = 0

		if self.macRequest == 1 and self['mac']:
			for macAddress in self['mac']:
				if macAddress:
					univention.admin.allocators.confirm(self.lo, self.position, 'mac', macAddress)
			self.macRequest = 0

		self.update_groups()

	def _ldap_post_remove(self):
		if self['mac']:
			for macAddress in self['mac']:
				if macAddress:
					univention.admin.allocators.release(self.lo, self.position, 'mac', macAddress)
		if self['ip']:
			for ipAddress in self['ip']:
				if ipAddress:
					univention.admin.allocators.release(self.lo, self.position, 'aRecord', ipAddress)

		# remove computer from groups
		groups = copy.deepcopy(self['groups'])
		if self.oldinfo.get('primaryGroup'):
			groups.append(self.oldinfo.get('primaryGroup'))
		for group in groups:
			groupObject = univention.admin.objects.get(univention.admin.modules.get('groups/group'), self.co, self.lo, self.position, group)
			groupObject.fast_member_remove([self.dn], self.oldattr.get('uid', []), ignore_license=1)

	def __update_groups_after_namechange(self):
		oldname = self.oldinfo.get('name')
		newname = self.info.get('name')
		if not oldname:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, '__update_groups_after_namechange: oldname is empty')
			return

		# Since self.dn is not updated yet, self.dn contains still the old DN.
		# Thats why olddn and newdn get reassebled from scratch.
		olddn = 'cn=%s,%s' % (escape_dn_chars(oldname), self.lo.parentDn(self.dn))
		newdn = 'cn=%s,%s' % (escape_dn_chars(newname), self.lo.parentDn(self.dn))

		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, '__update_groups_after_namechange: olddn=%s' % olddn)
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, '__update_groups_after_namechange: newdn=%s' % newdn)

		for group in self.info.get('groups', []):
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, '__update_groups_after_namechange: grp=%s' % group)

			# Using the UDM groups/group object does not work at this point. The computer object has already been renamed.
			# During open() of groups/group each member is checked if it exists. Because the computer object with "olddn" is missing,
			# it won't show up in groupobj['hosts']. That's why the uniqueMember/memberUid updates is done directly via
			# self.lo.modify()

			oldUniqueMembers = self.lo.getAttr(group, 'uniqueMember')
			newUniqueMembers = copy.deepcopy(oldUniqueMembers)
			if olddn in newUniqueMembers:
				newUniqueMembers.remove(olddn)
			if newdn not in newUniqueMembers:
				newUniqueMembers.append(newdn)

			oldUid = '%s$' % oldname
			newUid = '%s$' % newname
			oldMemberUids = self.lo.getAttr(group, 'memberUid')
			newMemberUids = copy.deepcopy(oldMemberUids)
			if oldUid in newMemberUids:
				newMemberUids.remove(oldUid)
			if newUid not in newMemberUids:
				newMemberUids.append(newUid)

			self.lo.modify(group, [('uniqueMember', oldUniqueMembers, newUniqueMembers), ('memberUid', oldMemberUids, newMemberUids)])

	def update_groups(self):
		if not self.hasChanged('groups') and not self.oldPrimaryGroupDn and not self.newPrimaryGroupDn:
			return
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'updating groups')

		old_groups = DN.set(self.oldinfo.get('groups', []))
		new_groups = DN.set(self.info.get('groups', []))

		if self.oldPrimaryGroupDn:
			old_groups += DN.set([self.oldPrimaryGroupDn])

		if self.newPrimaryGroupDn:
			new_groups.add(DN(self.newPrimaryGroupDn))

		# prevent machineAccountGroup from being removed
		if self.has_key('machineAccountGroup'):
			machine_account_group = DN.set([self['machineAccountGroup']])
			new_groups += machine_account_group
			old_groups -= machine_account_group

		for group in old_groups ^ new_groups:
			groupdn = str(group)
			groupObject = univention.admin.objects.get(univention.admin.modules.get('groups/group'), self.co, self.lo, self.position, groupdn)
			groupObject.open()
			# add this computer to the group
			hosts = DN.set(groupObject['hosts'] + [self.dn])
			if group not in new_groups:
				# remove this computer from the group
				hosts -= DN.set([self.dn])
			groupObject['hosts'] = list(DN.values(hosts))
			groupObject.modify(ignore_license=1)

	def primary_group(self):
		if not self.hasChanged('primaryGroup'):
			return
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'updating primary groups')

		primaryGroupNumber = self.lo.getAttr(self['primaryGroup'], 'gidNumber', required=True)
		self.newPrimaryGroupDn = self['primaryGroup']
		self.lo.modify(self.dn, [('gidNumber', 'None', primaryGroupNumber[0])])

		if 'samba' in self.options:
			primaryGroupSambaNumber = self.lo.getAttr(self['primaryGroup'], 'sambaSID', required=True)
			self.lo.modify(self.dn, [('sambaPrimaryGroupSID', 'None', primaryGroupSambaNumber[0])])

	def cleanup(self):
		self.open()
		if self['dnsEntryZoneForward']:
			for dnsEntryZoneForward in self['dnsEntryZoneForward']:
				dn, ip = self.__split_dns_line(dnsEntryZoneForward)
				try:
					self.__remove_dns_forward_object(self['name'], dn, None)
				except Exception, e:
					self.exceptions.append([_('DNS forward zone'), _('delete'), e])

		if self['dnsEntryZoneReverse']:
			for dnsEntryZoneReverse in self['dnsEntryZoneReverse']:
				dn, ip = self.__split_dns_line(dnsEntryZoneReverse)
				try:
					self.__remove_dns_reverse_object(self['name'], dn, ip)
				except Exception, e:
					self.exceptions.append([_('DNS reverse zone'), _('delete'), e])

		if self['dhcpEntryZone']:
			for dhcpEntryZone in self['dhcpEntryZone']:
				dn, ip, mac = self.__split_dhcp_line(dhcpEntryZone)
				try:
					self.__remove_from_dhcp_object(mac=mac)
				except Exception, e:
					self.exceptions.append([_('DHCP'), _('delete'), e])

		if self['dnsEntryZoneAlias']:
			for entry in self['dnsEntryZoneAlias']:
				dnsForwardZone, dnsAliasZoneContainer, alias = entry
				try:
					self.__remove_dns_alias_object(self['name'], dnsForwardZone, dnsAliasZoneContainer, alias)
				except Exception, e:
					self.exceptions.append([_('DNS Alias'), _('delete'), e])

		# remove service record entries (see Bug #26400)
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, '_ldap_post_remove: clean up service records, host records, and IP address saved at the forward zone')
		ips = set(self['ip'] or [])
		fqdn = self['fqdn']
		fqdnDot = '%s.' % fqdn  # we might have entires w/ or w/out trailing '.'

		# iterate over all reverse zones
		for zone in self['dnsEntryZoneReverse'] or []:
			# load zone object
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'clean up entries for zone: %s' % zone)
			if len(zone) < 1:
				continue
			zoneObj = univention.admin.objects.get(
				univention.admin.modules.get('dns/reverse_zone'), self.co, self.lo, self.position, dn=zone[0])
			zoneObj.open()

			# clean up nameserver records
			if 'nameserver' in zoneObj:
				if fqdnDot in zoneObj['nameserver']:
					univention.debug.debug(
						univention.debug.ADMIN,
						univention.debug.INFO,
						'removing %s from dns zone %s' % (fqdnDot, zone[0]))
					# nameserver is required in reverse zone
					if len(zoneObj['nameserver']) > 1:
						zoneObj['nameserver'].remove(fqdnDot)
						zoneObj.modify()

		# iterate over all forward zones
		for zone in self['dnsEntryZoneForward'] or []:
			# load zone object
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'clean up entries for zone: %s' % zone)
			if len(zone) < 1:
				continue
			zoneObj = univention.admin.objects.get(
				univention.admin.modules.get('dns/forward_zone'), self.co, self.lo, self.position, dn=zone[0])
			zoneObj.open()
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'zone aRecords: %s' % zoneObj['a'])

			zone_obj_modified = False
			# clean up nameserver records
			if 'nameserver' in zoneObj:
				if fqdnDot in zoneObj['nameserver']:
					univention.debug.debug(
						univention.debug.ADMIN,
						univention.debug.INFO,
						'removing %s from dns zone %s' % (fqdnDot, zone))
					# nameserver is required in forward zone
					if len(zoneObj['nameserver']) > 1:
						zoneObj['nameserver'].remove(fqdnDot)
						zone_obj_modified = True

			# clean up aRecords of zone itself
			new_entries = list(set(zoneObj['a']) - ips)
			if len(new_entries) != len(zoneObj['a']):
				univention.debug.debug(
					univention.debug.ADMIN,
					univention.debug.INFO,
					'Clean up zone records:\n%s ==> %s' % (zoneObj['a'], new_entries))
				zoneObj['a'] = new_entries
				zone_obj_modified = True

			if zone_obj_modified:
				zoneObj.modify()

			# clean up service records
			for irecord in univention.admin.modules.lookup('dns/srv_record', self.co, self.lo, base=self.lo.base, scope='sub', superordinate=zoneObj):
				irecord.open()
				new_entries = [j for j in irecord['location'] if fqdn not in j and fqdnDot not in j]
				if len(new_entries) != len(irecord['location']):
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'Entry found in "%s":\n%s ==> %s' % (irecord.dn, irecord['location'], new_entries))
					irecord['location'] = new_entries
					irecord.modify()

			# clean up host records (that should probably be done correctly by Samba4)
			for irecord in univention.admin.modules.lookup('dns/host_record', self.co, self.lo, base=self.lo.base, scope='sub', superordinate=zoneObj):
				irecord.open()
				new_entries = list(set(irecord['a']) - ips)
				if len(new_entries) != len(irecord['a']):
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'Entry found in "%s":\n%s ==> %s' % (irecord.dn, irecord['a'], new_entries))
					irecord['a'] = new_entries
					irecord.modify()

	def __setitem__(self, key, value):
		raise_after = None
		if key == 'network':
			if self.old_network != value:
				if value and value != 'None':
					network_object = univention.admin.handlers.networks.network.object(self.co, self.lo, self.position, value)
					network_object.open()

					if not self['ip'] or len(self['ip']) < 1 or not self['ip'][0] or not univention.admin.ipaddress.ip_is_in_network(network_object['network'], network_object['netmask'], self['ip'][0]):
						if self.ip_freshly_set:
							raise_after = univention.admin.uexceptions.ipOverridesNetwork
						else:
							# get next IP
							network_object.refreshNextIp()
							self['ip'] = network_object['nextIp']
							try:
								IpAddr = univention.admin.allocators.request(self.lo, self.position, 'aRecord', value=self['ip'][0])
								self.ip_alredy_requested = 1
								self.alloc.append(('aRecord', IpAddr))
								self.ip = IpAddr
							except:
								pass

						self.network_object = network_object
					if network_object['dnsEntryZoneForward']:
						if self.has_key('ip') and self['ip'] and len(self['ip']) == 1:
							self['dnsEntryZoneForward'] = [[network_object['dnsEntryZoneForward'], self['ip'][0]], ]
					if network_object['dnsEntryZoneReverse']:
						if self.has_key('ip') and self['ip'] and len(self['ip']) == 1:
							self['dnsEntryZoneReverse'] = [[network_object['dnsEntryZoneReverse'], self['ip'][0]], ]
					if network_object['dhcpEntryZone']:
						if self.has_key('ip') and self['ip'] and len(self['ip']) == 1 and self.has_key('mac') and self['mac'] and len(self['mac']) == 1:
							self['dhcpEntryZone'] = [(network_object['dhcpEntryZone'], self['ip'][0], self['mac'][0])]
						else:
							self.__saved_dhcp_entry = network_object['dhcpEntryZone']

					self.old_network = value

		elif key == 'ip':
			self.ip_freshly_set = True
			if not self.ip or self.ip != value:
				if self.ip_alredy_requested:
					univention.admin.allocators.release(self.lo, self.position, 'aRecord', self.ip)
					self.ip_alredy_requested = 0
				if value and self.network_object:
					if self.network_object['dnsEntryZoneForward']:
						if self.has_key('ip') and self['ip'] and len(self['ip']) == 1:
							self['dnsEntryZoneForward'] = [[self.network_object['dnsEntryZoneForward'], self['ip'][0]], ]
					if self.network_object['dnsEntryZoneReverse']:
						if self.has_key('ip') and self['ip'] and len(self['ip']) == 1:
							self['dnsEntryZoneReverse'] = [[self.network_object['dnsEntryZoneReverse'], self['ip'][0]]]
					if self.network_object['dhcpEntryZone']:
						if self.has_key('ip') and self['ip'] and len(self['ip']) == 1 and self.has_key('mac') and self['mac'] and len(self['mac']) > 0:
							self['dhcpEntryZone'] = [(self.network_object['dhcpEntryZone'], self['ip'][0], self['mac'][0])]
						else:
							self.__saved_dhcp_entry = self.network_object['dhcpEntryZone']
			if not self.ip or self.ip is None:
				self.ip_freshly_set = False

		elif key == 'mac' and self.__saved_dhcp_entry:
			if self.has_key('ip') and self['ip'] and len(self['ip']) == 1 and self['mac'] and len(self['mac']) > 0:
				if isinstance(value, list):
					self['dhcpEntryZone'] = [(self.__saved_dhcp_entry, self['ip'][0], value[0])]
				else:
					self['dhcpEntryZone'] = [(self.__saved_dhcp_entry, self['ip'][0], value)]

		super(simpleComputer, self).__setitem__(key, value)
		if raise_after:
			raise raise_after


class simpleLdapSub(simpleLdap):

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes=[]):
		base.__init__(self, co, lo, position, dn, superordinate)

	def _create(self):
		self._modify()

	def _remove(self, remove_childs=0):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, '_remove() called')
		self._ldap_pre_remove()

		ml = self._ldap_dellist()
		self.lo.modify(self.dn, ml)

		self._ldap_post_remove()


class simplePolicy(simpleLdap):

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes=[]):

		self.resultmode = 0
		self.dn = dn

		if not hasattr(self, 'cloned'):
			self.cloned = None

		if not hasattr(self, 'changes'):
			self.changes = 0

		if not hasattr(self, 'policy_attrs'):
			self.policy_attrs = {}

		if not hasattr(self, 'referring_object_dn'):
			self.referring_object_dn = None

		simpleLdap.__init__(self, co, lo, position, dn, superordinate, attributes)

	def copyIdentifier(self, from_object):
		"""Activate the result mode and set the referring object"""

		self.resultmode = 1
		for key, property in from_object.descriptions.items():
			if property.identifies:
				for key2, property2 in self.descriptions.items():
					if property2.identifies:
						self.info[key2] = from_object.info[key]
		self.referring_object_dn = from_object.dn
		if not self.referring_object_dn:
			self.referring_object_dn = from_object.position.getDn()
		self.referring_object_position_dn = from_object.position.getDn()

	def clone(self, referring_object):
		"""Marks the object as a not existing one containing values
		retrieved by evaluating the policies for the given object"""

		self.cloned = self.dn
		self.dn = ''
		self.copyIdentifier(referring_object)

	def getIdentifier(self):
		for key, property in self.descriptions.items():
			if property.identifies and key in self.info and self.info[key]:
				return key

	def __makeUnique(self):
		_d = univention.debug.function('admin.handlers.simplePolicy.__makeUnique')
		identifier = self.getIdentifier()
		components = self.info[identifier].split("_uv")
		if len(components) > 1:
			try:
				n = int(components[1])
				n += 1
			except ValueError:
				n = 1
		else:
			n = 0
		self.info[identifier] = "%s_uv%d" % (components[0], n)
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simplePolicy.__makeUnique: result: %s' % self.info[identifier])

	def create(self):
		if not self.resultmode:
			simpleLdap.create(self)
			return

		self._exists = False
		try:
			self.oldinfo = {}
			simpleLdap.create(self)
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simplePolicy.create: created object: info=%s' % (self.info))
		except univention.admin.uexceptions.objectExists:
			self.__makeUnique()
			self.create()

	def policy_result(self, faked_policy_reference=None):
		"""This method retrieves the policy values currently effective
		for this object. If the 'resultmode' is not active the evaluation
		is cancelled.

		If faked_policy_reference is given at the top object
		(referring_object_dn) this policy object temporarily referenced.

		faked_policy_reference can be a string or a list of strings."""

		if not self.resultmode:
			return

		self.polinfo_more = {}
		if not self.policy_attrs:
			policies = []
			if isinstance(faked_policy_reference, (list, tuple)):
				policies.extend(faked_policy_reference)
			elif faked_policy_reference:
				policies.append(faked_policy_reference)

			# the referring object does not exist yet
			if not self.referring_object_dn == self.referring_object_position_dn:
				result = self.lo.getPolicies(self.lo.parentDn(self.referring_object_dn), policies=policies)
			else:
				result = self.lo.getPolicies(self.referring_object_position_dn, policies=policies)
			for policy_oc, attrs in result.items():
				if univention.admin.objects.ocToType(policy_oc) == self.module:
					self.policy_attrs = attrs

		if hasattr(self, '_custom_policy_result_map'):
			self._custom_policy_result_map()
		else:
			values = {}
			for attr_name, value_dict in self.policy_attrs.items():
				values[attr_name] = value_dict['value']
				self.polinfo_more[self.mapping.unmapName(attr_name)] = value_dict

			self.polinfo = univention.admin.mapping.mapDict(self.mapping, values)
			self.polinfo = self._post_unmap(self.polinfo, values)

	def __getitem__(self, key):
		if not self.resultmode:
			if self.has_key('emptyAttributes') and self.mapping.mapName(key) and self.mapping.mapName(key) in simpleLdap.__getitem__(self, 'emptyAttributes'):
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simplePolicy.__getitem__: empty Attribute %s' % key)
				if self.descriptions[key].multivalue:
					return []
				else:
					return ''
			return simpleLdap.__getitem__(self, key)

		self.policy_result()

		if (key in self.polinfo and not (key in self.info or key in self.oldinfo)) or (key in self.polinfo_more and 'fixed' in self.polinfo_more[key] and self.polinfo_more[key]['fixed']):
			if self.descriptions[key].multivalue and not isinstance(self.polinfo[key], types.ListType):
				# why isn't this correct in the first place?
				self.polinfo[key] = [self.polinfo[key]]
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simplePolicy.__getitem__: presult: %s=%s' % (key, self.polinfo[key]))
			return self.polinfo[key]

		result = simpleLdap.__getitem__(self, key)
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'simplePolicy.__getitem__: result: %s=%s' % (key, result))
		return result

	def fixedAttributes(self):
		'''return effectively fixed attributes. '''

		if not self.resultmode:
			return {}

		fixed_attributes = {}
		if not self.policy_attrs:
			if not self.referring_object_dn == self.referring_object_position_dn:
				result = self.lo.getPolicies(self.lo.parentDn(self.referring_object_dn))
			else:
				result = self.lo.getPolicies(self.referring_object_position_dn)
			for key, value in result.items():
				if univention.admin.objects.ocToType(key) == self.module:
					self.policy_attrs = value

		for attr_name, value_dict in self.policy_attrs.items():
			if value_dict.has_key('fixed'):
				fixed_attributes[self.mapping.unmapName(attr_name)] = value_dict['fixed']
			else:
				fixed_attributes[self.mapping.unmapName(attr_name)] = 0

		return fixed_attributes

	def emptyAttributes(self):
		'''return effectively empty attributes. '''

		empty_attributes = {}

		if self.has_key('emptyAttributes'):
			for attrib in simpleLdap.__getitem__(self, 'emptyAttributes'):
				empty_attributes[self.mapping.unmapName(attrib)] = 1

		return empty_attributes

	def __setitem__(self, key, newvalue):
		if not self.resultmode:
			simpleLdap.__setitem__(self, key, newvalue)
			return

		self.policy_result()

		if self.polinfo.has_key(key):

			if self.polinfo[key] != newvalue or self.polinfo_more[key]['policy'] == self.cloned or (self.info.has_key(key) and self.info[key] != newvalue):
				if self.polinfo_more[key]['fixed'] and self.polinfo_more[key]['policy'] != self.cloned:
					raise univention.admin.uexceptions.policyFixedAttribute, key
				simpleLdap.__setitem__(self, key, newvalue)
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'polinfo: set key %s to newvalue %s' % (key, newvalue))
				if self.hasChanged(key):
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'polinfo: key:%s hasChanged' % (key))
					self.changes = 1
			return

		# this object did not exist before
		if not self.oldinfo:
			# if this attribute is of type boolean and the new value is equal to the default, than ignore this "change"
			if isinstance(self.descriptions[key].syntax, univention.admin.syntax.boolean):
				if self.descriptions.has_key(key):
					default = self.descriptions[key].base_default
					if type(self.descriptions[key].base_default) in (tuple, list):
						default = self.descriptions[key].base_default[0]
					if (not default and newvalue == '0') or default == newvalue:
						return

		simpleLdap.__setitem__(self, key, newvalue)
		if self.hasChanged(key):
			self.changes = 1


class _MergedAttributes(object):

	"""Evaluates old attributes and the modlist to get a new representation of the object."""

	def __init__(self, obj, modlist):
		self.obj = obj
		self.modlist = [x if len(x) == 3 else (x[0], None, x[-1]) for x in modlist]
		self.case_insensitive_attributes = ['objectClass']

	def get_attributes(self):
		attributes = set(self.obj.oldattr.keys()) | set(x[0] for x in self.modlist)
		return dict((attr, self.get_attribute(attr)) for attr in attributes)

	def get_attribute(self, attr):
		values = set(self.obj.oldattr.get(attr, []))
		# evaluate the modlist and apply all changes to the current values
		for (att, old, new) in self.modlist:
			if att.lower() != attr.lower():
				continue
			new = [] if not new else [new] if isinstance(new, basestring) else new
			old = [] if not old else [old] if isinstance(old, basestring) else old
			if not old and new:  # MOD_ADD
				values |= set(new)
			elif not new and old:  # MOD_DELETE
				values -= set(old)
			elif old and new:  # MOD_REPLACE
				values = set(new)
		return list(values)


if __name__ == '__main__':
	import doctest
	doctest.testmod()
