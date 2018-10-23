# -*- generated by 1.0.12 -*-
import da
_config_object = {}

class CoreRBAC(da.DistProcess):

    def __init__(self, procimpl, props):
        super().__init__(procimpl, props)
        self._events.extend([])

    def setup(self, **rest_942):
        super().setup(**rest_942)
        self._state.USERS = set()
        self._state.ROLES = set()
        self._state.PERMS = set()
        self._state.UR = set()
        self._state.PR = set()

    def AddUser(self, user):
        self._state.USERS.add(user)

    def DeleteUser(self, user):
        self._state.UR -= {(user, r) for r in self._state.ROLES}
        USERs.remove(user)

    def AddRole(self, role):
        self._state.ROLES.add(role)

    def DeleteRole(self, role):
        self._state.UR -= {(u, role) for u in self._state.USERS}
        self._state.PR -= {(p, role) for p in self._state.PERMS}
        self._state.ROLES.remove(role)

    def AddPerm(self, perm):
        self._state.PERMS.add(perm)

    def DeletePerm(self, perm):
        self._state.PR -= {(perm, r) for r in self._state.ROLES}
        self._state.PERMS.remove(perm)

    def AddUR(self, user, role):
        self._state.UR.add((user, role))

    def DeleteUR(self, user, role):
        self._state.UR.remove((user, role))

    def AddPR(self, perm, role):
        self._state.PR.add((perm, role))

    def DeleteUR(self, perm, role):
        self._state.PR.remove((perm, role))

    def AssignedUsers(self, role):
        'the set of users assigned to role in UR'
        return {u for (u, _BoundPattern357_) in self._state.UR if (_BoundPattern357_ == role)}

    def AssignedRoles(self, user):
        'the set of roles assigned to user in UR'
        return {r for (_BoundPattern370_, r) in self._state.UR if (_BoundPattern370_ == user)}

    def UserPermissions(self, user):
        'the set of permissions assigned to the roles assigned to user'
        return {p for (_BoundPattern385_, r) in self._state.UR if (_BoundPattern385_ == user) for (p, _FreePattern394_) in self._state.PR if (_FreePattern394_ == r)}

class HierarchicalRBAC(CoreRBAC, da.DistProcess):

    def __init__(self, procimpl, props):
        super().__init__(procimpl, props)
        self._events.extend([])

    def setup(self, RH, **rest_942):
        super().setup(RH=RH, **rest_942)
        self._state.RH = RH
        super.setup()
        self._state.RH = set()

    def run(self):
        print('U', USERS)
        print('R', ROLES)
        print('UR', UR)
        print('RH', self._state.RH)
        print(self.AuthorizedUsers(r2))
        print(self.AuthorizedUsers(r1))

    def AddInheritance(self, a, d):
        self._state.RH.add((a, d))

    def DeleteInheritance(self, a, d):
        self._state.RH.remove((a, d))

    def AuthorizedUsers(self, role):
        'the set of users of role or ascendant roles of role'
        return {u for (u, asc) in UR for (_FreePattern464_, _BoundPattern465_) in trans(self._state.RH) if (_FreePattern464_ == asc) if (_BoundPattern465_ == role)}

    def trans1(self, E):
        self.infer()
        self.infer(edge=E)
        self.infer(path)
        self.infer(path, edge=E)
        trans = self.infer(path, edge=E)
        trans = self.infer(path(_, _), edge=E)
        a = 888
        b = 999
        (areach, reachb) = self.infer(path(a, _), path(_, b), edge=E)
        (areach, reachb) = self.infer(path(a, _), path(_, b), edge=E, filenmae='tmp')
        return (trans, areach, reachb)

    def infer(self, rules={}):
        '\n    for input using keyword arguments:\n    if keyword arguments are given, use the given arguments as input,\n    otherwise if named attributes are defined, use defined attributes ?\n    otherwise, use empty sets ?  no, treat as undefined\n    for output using non-keyword arguments:\n    if non-keyward arguments are given, return a set of tuples for each arg,\n    otherwise, write to named attributes of the inferred sets of tuples\n    '
        pass

class HRBAC_py(HierarchicalRBAC):

    def trans(E):
        T = E
        W = ({(x, d) for (x, y) in T for (a, d) in E if (y == a)} - T)
        while W:
            T.add(W.pop())
            W = ({(x, d) for (x, y) in T for (a, d) in E if (y == a)} - T)
        return (T | {(r, r) for r in self.ROLES})

    def AuthorizedUsers(role):
        return set((u for u in self.USERS for asc in self.ROLES if (((asc, role) in self.trans(RH)) and ((u, asc) in self.UR))))

class HRBAC_set(HierarchicalRBAC):

    def trans(E):
        'the transitive closure of role hierarchy E union reflexive role pairs\n    '
        T = E
        x = y = z = None

        def ExistentialOpExpr_735():
            nonlocal x, y, z
            for (x, y) in T:
                for (_FreePattern746_, z) in E:
                    if (_FreePattern746_ == y):
                        if (not ((x, z) in T)):
                            return True
            return False
        while ExistentialOpExpr_735():
            T.add((x, z))
        return (T | {(r, r) for r in ROLES})

    def AuthorizedUsers(role):
        'the set of users of role or ascendant roles of role'
        return {u for (u, asc) in UR for (_FreePattern796_, _BoundPattern797_) in trans(RH) if (_FreePattern796_ == asc) if (_BoundPattern797_ == role)}

    def AuthorizedRoles(user):
        'the set of roles of user or descendant roles of the roles'
        return {r for (_BoundPattern815_, asc) in UR if (_BoundPattern815_ == user) for (_FreePattern823_, r) in trans(RH) if (_FreePattern823_ == asc)}

class HRBAC_set_maint(HRBAC_set):

    def setup(RH):
        super.setup()
        self.transRH = set()

    def AddInheritance(a, d):
        super.AddInheritance(a, d)
        transRH = trans(RH)

    def DeleteInheritance(a, d):
        super.DeleteInheritance(a, d)
        transRH = trans(RH)

    def AuthorizedUsers(role):
        return {u for (u, r) in UR for (_FreePattern905_, _BoundPattern906_) in transRH if (_FreePattern905_ == r) if (_BoundPattern906_ == role)}
"\nclass HRBAC_transRH_rules(HRBAC_set_maint):\n\n# in ideal syntax:\n#\n#  rules myname (declarations):\n#    transRH(x,y) if RH(x,y)\n#    transRH(x,y) if RH(x,z), transRH(z,y)\n#\n#    if RH(x,y): transRH(x,y) \n#    if RH(x,z), transRH(z,y): transRH(x,y) \n\n  def AddInheritance(a,d):\n    # pre: a in ROLES, d in ROLES, (a,d) not in RH, (d,a) not in RH, a!=d\n    super.AddInheritance(a,d)\n    infer(rules=transRH_rules)\n    # transRH = infer(transRH, RH=RH rules=transRH_rules)\n\n  def DeleteInheritance(a,d):  # pre: (a,d) in RH\n    super.DeleteInheritance(a,d)\n    infer(rules=transRH_rules)\n\n  def rules (name=transRH_rules):\n    transRH(x,y), if_(RH(x,y))\n    transRH(x,y), if_(RH(x,z), transRH(z,y))\n    transRH(x,x), if_(ROLES(x)) # with this base case, don't need first rule\n\nclass HRBAC_trans_rules(HRBAC_set):\n\n  def rules (name=trans_rules, edge=['certain',(int,int)], path='certain'):\n    path(x,y), if_(edge(x,y))\n    path(x,y), if_(edge(x,z), path(z,y))\n\n  def trans(E):  # use infer plus set query\n    return infer(path, edge=E, rules=trans_rules) | setof((r,r), r in ROLES)\n\n# not allow, as it would be equivalent to dynamic scoping:\n#\n#  def trans2(edge):\n#    return infer(path) | setof((r,r), r in ROLES)\n\nclass HRBAC_trans_with_role_rules(HRBAC_set):\n\n  def rules (name=trans_with_role_rules): # with additional last rule\n    path(x,y), if_(edge(x,y))\n    path(x,y), if_(edge(x,z), path(z,y))\n    path(x,y), if_(role(x))\n\n  def trans(E):  # use infer only, pass in also ROLES\n    return infer(path, edge=E, role=ROLES, rules=trans_with_role_rules)\n\nclass HRBAC_trans_with_ROLES_rules(HRBAC_set):\n\n  def rules (name=trans_with_ROLES_rules):\n    path(x,y), if_(edge(x,y))\n    path(x,y), if_(edge(x,z),path(z,y))\n    path(x,x), if_(ROLES(x))\n\n  def trans(E):\n    return infer(path, edge=E, rules=trans_with_ROLES_rules)\n\nclass HRBAC_transRH_with_edge_rules(HRBAC_set):\n\n  def rules (name=transRH_with_edge_rules):\n    transRH(x,y), if_(edge(x,y))\n    transRH(x,y), if_(edge(x,z), transRH(z,y))\n    transRH(x,x), if_(ROLES(x))\n\n  def trans(E):\n    return infer(path, edge=E, rules=trans_with_edge_rules)\n\nclass HRBAC_trans_with_RH_ROLES_rules(HRBAC_set):\n\n  def rules (name=trans_with_RH_ROLES_rules):\n    path(x,y), if_(RH(x,y))\n    path(x,y), if_(RH(x,z),path(z,y))\n    path(x,x), if_(ROLES(x))\n\n  def trans(E):\n    return infer(path, rules=trans_with_RH_ROLES_rules)\n"

class Node_(da.NodeProcess):

    def __init__(self, procimpl, props):
        super().__init__(procimpl, props)
        self._events.extend([])

    def run(self):
        o = self.new(HierarchicalRBAC)
        '\n  o1 = new(HRBAC_transRH_rules,[])\n  o2 = new(HRBAC_trans_rules)\n  o3 = new(HRBAC_trans_with_role_rules)\n  '
        o41 = self.new(HRBAC_set)
        o42 = self.new(HRBAC_set_maint)
        o43 = self.new(HRBAC_py)
        self._start(o)