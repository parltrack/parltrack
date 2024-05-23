
def run(ctx):
    from collections import defaultdict
    res = defaultdict(lambda: defaultdict(int))
    keys = set()

    for d in ctx.iterate_json('ep_mep_activities'):
        m = d['mep_id']
        for ak, aa in d.items():
            if ak in ('mep_id', 'meta', 'changes'):
                continue
            keys.add(ak)
            for a in aa:
                if a['term'] != 9:
                    continue
                res[m][ak] += 1

    ctx.write_line('NAME,COUNTRY,GROUP,PARTY,' + ','.join(keys))

    for mep in ctx.iterate_json('ep_meps'):
        if mep['UserID'] not in res:
            continue

        activity = res[mep['UserID']]
        name = mep['Name']['full']
        group = ctx.latest(mep['Groups'])['groupid']
        party = ctx.latest(mep['Constituencies'])['party']
        country = ctx.latest(mep['Constituencies'])['country']

        ctx.write_line(','.join([x.replace(',', ' ') for x in [name, country, group, party, *[str(activity[k]) for k in keys]]]))

