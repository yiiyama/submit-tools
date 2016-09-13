function initPage()
{
    var inputData = {
        'search': 'users'
    };

    $.get('search.php', inputData, function (data, textStatus, jqXHR) {
            displayUsers(data);
        }, 'json');

    var table = d3.select('#clusterList')
        .style('height', '42px');

    var tableNode = table.node();

    var headRow = table.select('thead').append('tr');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.05 - 1) + 'px')
        .append('input')
        .attr({'type': 'checkbox', 'id': 'selectAllClusters'})
        .on('change', function () {
                var check = d3.selectAll('#clusterList tbody tr td.select input');
                check.property('checked', d3.select(this).property('checked'));
                loadJobs();
            });

    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.15 - 1) + 'px')
        .text('ClusterId');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.15 - 1) + 'px')
        .text('User');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.3 - 1) + 'px')
        .text('Executable');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.2 - 1) + 'px')
        .text('Submit date');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.15 - 1) + 'px')
        .text('Jobs');

    table = d3.select('#jobList')
        .style('height', '42px');

    tableNode = table.node();

    headRow = table.select('thead').append('tr');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.08 - 1) + 'px')
        .text('ClusterId');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.08 - 1) + 'px')
        .text('ProcId');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.08 - 1) + 'px')
        .text('User');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.08 - 1) + 'px')
        .text('Executable');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.13 - 1) + 'px')
        .text('Start time');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.05 - 1) + 'px')
        .text('Succeeded');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.2 - 1) + 'px')
        .text('CPU time');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.2 - 1) + 'px')
        .text('Wallclock time');
    headRow.append('th')
        .style('width', (tableNode.clientWidth * 0.1 - 1) + 'px')
        .text('Exit code');
}

function displayUsers(users)
{
    var box = d3.select('#users');
    var textHeight = parseInt(window.getComputedStyle(box.node()).fontSize, 10);
    if (users.length > 5) {
        box.style('height', (textHeight * 6) + 'px');
    }
    else
        box.style('height', (textHeight * (users.length + 1)) + 'px');

    var lines = box.selectAll('div.user')
        .data(users)
        .enter().append('div').classed('user', true);

    lines.append('input').attr('type', 'checkbox')
        .property('value', function (d) { return d.name; })
        .on('change', function () { findClusters(); });

    lines.append('span')
        .text(function (d) { return d.name; });
}

var findClusterBlocked = false;
var clusterSearchKeys = {
    'search': 'clusters',
    'users': [],
    'cmds': []
};

function findClusters()
{
    if (findClusterBlocked) {
        setTimeout(function () { findClusters(); }, 1000);
        return;
    }

    findClusterBlocked = true;
    setTimeout(function () { findClusterBlocked = false; }, 1000);

    var search = {'users': [], 'cmds': []};

    d3.select('#users').selectAll('input')
        .each(function () {
                if (this.checked)
                    search.users.push(this.value);
            });

    var cmdstr = $.trim(d3.select('#cmds').property('value'));
    if (cmdstr != '') {
        search.cmds = cmdstr.split(' ');
        search.cmds.sort();
    }

    var changed = false;
    for (var key in search) {
        current = clusterSearchKeys[key];
        if (current.length == search[key].length) {
            var x = 0;
            for (x = 0; x != current.length; ++x) {
                if (search[key][x] != current[x])
                    break;
            }
            if (x == current.length)
                continue;
        }

        changed = true;
    }

    if (!changed)
        return;

    clusterSearchKeys.users = search.users;
    clusterSearchKeys.cmds = search.cmds;

    var spinner = new Spinner({'scale': 5, 'corners': 0, 'width': 2, 'position': 'relative', 'top': '-50%', 'left': '50%'});
    spinner.spin();
    $('#clusterSelect').append($(spinner.el));

    $.get('search.php', clusterSearchKeys, function (data, textStatus, jqXHR) {
            showClusters(data);
            spinner.stop();
        }, 'json');
}

function showClusters(data)
{
    var table = d3.select('#clusterList');

    var rows = table.select('tbody').selectAll('tr')
        .remove()
        .data(data)
        .enter()
        .append('tr')
        .attr('id', function (d) { return 'cluster' + d.cid; });

    var tableNode = table.node();

    rows.append('td')
        .classed('select', true)
        .style({'width': (tableNode.clientWidth * 0.05 - 1) + 'px', 'padding': 0})
        .append('input')
        .attr('type', 'checkbox')
        .on('change', function () { loadJobs(); });
    rows.append('td')
        .classed('clusterId', true)
        .style('width', (tableNode.clientWidth * 0.15 - 11) + 'px')
        .text(function (d) { return d.cid; });
    rows.append('td')
        .style('width', (tableNode.clientWidth * 0.15 - 11) + 'px')
        .text(function (d) { return d.user; });
    rows.append('td')
        .style('width', (tableNode.clientWidth * 0.3 - 11) + 'px')
        .text(function (d) { return d.cmd; });
    rows.append('td')
        .style('width', (tableNode.clientWidth * 0.2 - 11) + 'px')
        .text(function (d) { return d.timestamp; });
    rows.append('td')
        .text(function (d) { return d.njobs; });
}

function loadJobs()
{
    d3.select('#jobList tbody').selectAll('tr')
        .remove();

    var clusterIds = [];
    d3.selectAll('#clusterList tbody tr')
        .each(function () {
                var thissel = d3.select(this);
                if (thissel.select('td.select input').property('checked'))
                    clusterIds.push(0 + thissel.select('.clusterId').text());
            });

    if (clusterIds.length == 0)
        return;
    
    var spinner = new Spinner({'scale': 5, 'corners': 0, 'width': 2, 'position': 'absolute'});
    spinner.spin();
    $('#jobView').append($(spinner.el));

    var inputData = {
        'search': 'jobs',
        'clusterIds': clusterIds
    };

    $.ajax({'url': 'search.php', 'data': inputData, 'success': function (data, textStatus, jqXHR) {
                showJobs(data, 'table');
                spinner.stop();
            }, 'dataType': 'json', 'async': false});
}

function showJobs(data, area)
{
    if (area == 'table') {
        var table = d3.select('#jobList');
        var rows = table.select('tbody').selectAll('tr')
            .remove()
            .data(data)
            .enter()
            .append('tr');

        var tableNode = table.node();

        rows.append('td')
            .style('width', (tableNode.clientWidth * 0.08 - 11) + 'px')
            .text(function (d) { return d.cid; });
        rows.append('td')
            .style('width', (tableNode.clientWidth * 0.08 - 11) + 'px')
            .text(function (d) { return d.pid; });
        rows.append('td')
            .style('width', (tableNode.clientWidth * 0.08 - 11) + 'px')
            .text(function (d) { return d.user; });
        rows.append('td')
            .style('width', (tableNode.clientWidth * 0.08 - 11) + 'px')
            .text(function (d) { return d.cmd; });
        rows.append('td')
            .style({'width': (tableNode.clientWidth * 0.13 - 11) + 'px', 'text-align': 'center'})
            .text(function (d) { return d.matchTime; });
        rows.append('td')
            .style({'width': (tableNode.clientWidth * 0.05 - 11) + 'px', 'text-align': 'center'})
            .text(function (d) { return d.success; });
        rows.append('td')
            .style('width', (tableNode.clientWidth * 0.2 - 11) + 'px')
            .text(function (d) { return d.cputime; });
        rows.append('td')
            .style('width', (tableNode.clientWidth * 0.2 - 11) + 'px')
            .text(function (d) { return d.walltime; });
        rows.append('td')
            .style('width', (tableNode.clientWidth * 0.1 - 11) + 'px')
            .text(function (d) { return d.exitcode; });
    }
}
