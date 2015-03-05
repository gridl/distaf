import re
from libs.client_rpyc import big_bang
testcases = []
tc = big_bang()


def testcase(name):
    def decorator(func):
        def wrapper(self):
            ret = func()
            self.assertTrue(ret, "Testcase %s failed" % name)
            return ret
        testcases.append((name, wrapper))
        return wrapper
    return decorator


def create_volume(volname, dist, rep=1, stripe=1, trans='tcp', servers=[], snap=True):
    """
        Create the gluster volume specified configuration
        volname and distribute count are mandatory argument
    """
    global tc
    if servers == []:
        servers = tc.nodes[:]
    dist = int(dist)
    rep = int(rep)
    stripe = int(stripe)
    number_of_bricks = dist * rep * stripe
    replica = stripec = ''
    brick_root = '/bricks'
    n = 0
    tempn = 0
    bricks_list = ''
    rc = tc.run(servers[0], "gluster volume info | egrep \"^Brick[0-9]+\"", \
            verbose=False)
    for i in range(0, number_of_bricks):
        if not snap:
            bricks_list = "%s %s:%s/%s_brick%d" % \
                (bricks_list, servers[n], brick_root, volname, i)
        else:
            sn = len(re.findall(servers[n], rc[1])) + tempn
            bricks_list = "%s %s:%s/brick%d/%s_brick%d" % \
            (bricks_list, servers[n], brick_root, sn, volname, i)
        if n < len(servers[:]) - 1:
            n = n + 1
        else:
            n = 0
            tempn = tempn + 1
    if rep != 1:
        replica = "replica %d" % rep
    if stripe != 1:
        stripec = "stripe %d" % stripe
    ttype = "transport %s" % trans
    ret = tc.run(servers[0], "gluster volume create %s %s %s %s %s" % \
                (volname, replica, stripec, ttype, bricks_list))
    return ret

def add_brick(volname, nbricks, replica=1, stripe=1, peers=[], mnode=''):
    """
        Does the gluster add-brick. If peer is '', peers from the config
        is taken. And replica/stripe will not be used by default.
        Returns the output of add-brick command, which would be a tuple of
        (retcode, stdout, sstderr) from gluster add-brick command.
    """
    global tc
    if peers == []:
        peers = tc.peers[:]
    if mnode == '':
        mnode = tc.nodes[0]
    replica = int(replica)
    stripe = int(stripe)
    volinfo = tc.run(mnode, "gluster volume info | egrep \"^Brick[0-9]+\"", \
            verbose=False)
    if volinfo[0] != 0:
        tc.logger.error("Unable to get volinfo for add-brick")
        return (-1, -1, -1)
    bi = int(re.findall(r"%s_brick([0-9]+)" % volname, volinfo[1])[-1]) + 1
    tempn = 0
    n = 0
    add_bricks = ''
    brick_root = "/bricks"
    for i in range(bi, bi + nbricks):
        sn = len(re.findall(r"%s" % peers[n], volinfo[1])) + tempn
        add_bricks = "%s %s:%s/brick%d/%s_brick%d" % (add_bricks, peers[n], \
                brick_root, sn, volname, i)
        if n < len(peers[:]) - 1:
            n = n + 1
        else:
            n = 0
            tempn = tempn + 1
    repc = strc = ''
    if replica != 1:
        repc = "replica %d" % replica
    if stripe != 1:
        stric = "stripe %d" % stripe
    ret = tc.run(mnode, "gluster volume add-brick %s %s %s %s" % \
            (volname, repc, strc, add_bricks))
    return ret


def mount_volume(volname, mtype='glusterfs', mpoint='/mnt/glusterfs', mserver='', mclient='', options=''):
    """
        Mount the gluster volume with specified options
        Takes the volume name as mandatory argument

        Returns a tuple of (returncode, stdout, stderr)
        Returns (0, '', '') if already mounted
    """
    global tc
    if mserver == '':
        mserver = tc.nodes[0]
    if mclient == '':
        mclient = tc.clients[0]
    if options != '':
        options = "-o %s" % options
    if mtype == 'nfs' and options != '':
        options = "%s,vers=3" % options
    elif mtype == 'nfs' and options == '':
        options = '-o vers=3'
    ret, _, _ = tc.run(mclient, "mount | grep %s | grep %s | grep \"%s\"" \
                % (volname, mpoint, mserver))
    if ret == 0:
        tc.logger.debug("Volume %s is already mounted at %s" \
        % (volname, mpoint))
        return (0, '', '')
    mcmd = "mount -t %s %s %s:%s %s" % (mtype, options, mserver,volname, mpoint)
    tc.run(mclient, "test -d %s || mkdir -p %s" % (mpoint, mpoint))
    return tc.run(mclient, mcmd)


def bring_down_brick(volname, bindex, node=''):
    """
        Kills the glusterfsd process of the particular brick
        Returns True on success and False on failure
    """
    global tc
    if node == '':
        node = tc.nodes[0]
    ret, rnode, _ = tc.run(node, "gluster volume info %s | egrep \"^Brick%d\" | \
    awk '{print $2}' | awk -F : '{print $1}'" % (volname, bindex))
    if ret != 0:
        return False
    ret, _, _ = tc.run(rnode.rstrip(), \
    "pid=`cat /var/lib/glusterd/vols/%s/run/*%s_brick%d.pid` && kill -15 $pid \
    || kill -9 $pid" % (volname, volname, bindex - 1))
    if ret != 0:
        return False
    else:
        return True

def start_glusterd(server=''):
    """
        Starts glusterd in all servers if they are not running

        Returns True if glusterd started in all servers
        Returns False if glusterd failed to start in any server

        (Will be enhanced to support systemd in future)
    """
    global tc
    if server == '':
        ret, _ = tc.run_servers("pgrep glusterd || /etc/init.d/glusterd start")
    else:
        ret = tc.run(server, "pgrep glusterd || /etc/init.d/glusterd start")
        if ret[0] != 0:
            ret = False
        else:
            ret = True
    return ret

def peer_probe(pnode='', servers=''):
    """
        Does peer probe and validates the same

        Returns True on success and False of failure
    """
    global tc
    if pnode == '':
        pnode = tc.nodes[0]
    if servers == '':
        servers = tc.nodes[1:]
    rc = True
    for peer in servers:
        ret = tc.run(pnode, "gluster peer probe %s" % peer)
        if ret[0] != 0:
            tc.logger.error("peer probe to machine %s failed" % peer)
            rc = False
    return rc

def get_service_status(volname, services="ALL", servers=tc.nodes):
    if services == "ALL":
        services = ["NFS", "Quota", "Self-heal", "Brick"]
    else:
        services = single_element_to_list_converter(services)
        servers = single_element_to_list_converter(servers)
    for service in services:
        print service
        flag = tc.run(servers[0], "gluster vol status %s | grep %s " % \
                (volname, service))
        if flag[0] == 0:
            flag = tc.run(servers[0], \
"gluster vol status %s | grep %s | egrep '[[:space:]]+N[[:space:]]+'" \
% (volname, service))
            if flag[0] == 0:
                for server in servers:
                    if service != "Brick" and server == servers[0]:
                        server = "localhost"
                    if re.search(server, flag[1]):
                        return False
        ### if service is not listed in vol status return false
        else:
            return False
    return True

def single_element_to_list_converter(input):
    if not isinstance(input, list):
        input = [input]
    return input
