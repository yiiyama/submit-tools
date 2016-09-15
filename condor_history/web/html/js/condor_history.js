var clusterListHeadWidths = [0.05, 0.15, 0.15, 0.25, 0.25, 0.15];
var clusterListBodyWidths = [0.05, 0.15, 0.15, 0.25, 0.25];
var jobListWidths = [0.05, 0.05, 0.05, 0.1, 0.1, 0.15, 0.2, 0.05, 0.1, 0.1, 0.05];

function initPage()
{
    // Get users

    var inputData = {
        'search': 'users'
    };

    $.get('search.php', inputData, function (data, textStatus, jqXHR) {
            displayUsers(data.users);
        }, 'json');

    // Set up date picker

    $.datepicker.setDefaults({'dateFormat': 'yy/mm/dd'});

    var begin = $('#submitBegin');
    begin.datepicker({'defaultDate': -1});
    begin.datepicker('setDate', -1);
    begin.val($.datepicker.formatDate('yy/mm/dd', begin.datepicker('getDate')));
    var end = $('#submitEnd');
    end.datepicker({'defaultDate': new Date()});
    end.datepicker('setDate', new Date());
    end.val($.datepicker.formatDate('yy/mm/dd', end.datepicker('getDate')));

    // Set up tables

    var table = d3.select('#clusterList')
        .style('height', '42px');

    var headRow = table.select('thead').append('tr');
    headRow.append('th')
        .append('input')
        .attr({'type': 'checkbox', 'id': 'selectAllClusters'})
        .on('change', function () {
                var check = d3.selectAll('#clusterList tbody tr td.select input');
                check.property('checked', d3.select(this).property('checked'));
                loadJobs();
            });

    headRow.append('th').text('ClusterId');
    headRow.append('th').text('User');
    headRow.append('th').text('Executable');
    headRow.append('th').text('Submit date');
    headRow.append('th').text('#Jobs');

    setColumnWidths(table, headRow, clusterListHeadWidths);

    table = d3.select('#jobList')
        .style('height', '42px');

    headRow = table.select('thead').append('tr');

    headRow.append('th').text('ClusterId');
    headRow.append('th').text('ProcId');
    headRow.append('th').text('User');
    headRow.append('th').text('Executable');
    headRow.append('th').text('Start date');
    headRow.append('th').text('Frontend');
    headRow.append('th').text('Site');
    headRow.append('th').text('Success');
    headRow.append('th').text('CPU time');
    headRow.append('th').text('Wallclock time');
    headRow.append('th').text('Exit code');

    setColumnWidths(table, headRow, jobListWidths);

    headRow = table.select('thead').append('tr');

    headRow.append('th').text('Total');
    headRow.append('th').classed('totalJobs', true);
    headRow.append('th');
    headRow.append('th');
    headRow.append('th');
    headRow.append('th');
    headRow.append('th');
    headRow.append('th').classed('totalSuccess', true).style('text-align', 'right');
    headRow.append('th').classed('totalCPUTime', true).style('text-align', 'right');
    headRow.append('th').classed('totalWallTime', true).style('text-align', 'right');
    headRow.append('th');

    setColumnWidths(table, headRow, jobListWidths);
    headRow.selectAll('th').style({'color': 'black', 'background-color': '#ffffff'});

    findClusters();
    loadJobs();
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
    'cmds': [],
    'ids': [],
    'begin': '',
    'end': ''
};

function findClusters()
{
    if (findClusterBlocked) {
        setTimeout(function () { findClusters(); }, 1000);
        return;
    }

    findClusterBlocked = true;
    setTimeout(function () { findClusterBlocked = false; }, 1000);

    var search = {'users': [], 'cmds': [], 'ids': [], 'begin': '', 'end': ''};

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

    var idstr = $.trim(d3.select('#clusterIds').property('value'));
    if (idstr != '') {
        var idstrs = idstr.split(' ');
        for (var x in idstrs) {
            var i = parseInt(idstrs[x]);
            if (i == i)
                search.ids.push(i);
        }
        search.ids.sort();
    }

    search.begin = $.trim(d3.select('#submitBegin').property('value'));
    search.end = $.trim(d3.select('#submitEnd').property('value'));

    var changed = false;
    for (var key in search) {
        current = clusterSearchKeys[key];
        if (Array.isArray(current)) {
            if (current.length == search[key].length) {
                var x = 0;
                for (x = 0; x != current.length; ++x) {
                    if (search[key][x] != current[x])
                        break;
                }
                if (x == current.length)
                    continue;
            }
        }
        else if (current == search[key])
            continue;

        changed = true;
        break;
    }

    if (!changed)
        return;

    d3.select('#clusterList tbody').selectAll('tr')
        .remove();

    clusterSearchKeys.users = search.users;
    clusterSearchKeys.cmds = search.cmds;
    clusterSearchKeys.ids = search.ids;
    clusterSearchKeys.begin = search.begin;
    clusterSearchKeys.end = search.end;

    var spinner = new Spinner({'scale': 5, 'corners': 0, 'width': 2, 'position': 'relative', 'top': '-50%', 'left': '50%'});
    spinner.spin();
    $('#clusterSelect').append($(spinner.el));

    $.get('search.php', clusterSearchKeys, function (data, textStatus, jqXHR) {
            showClusters(data.clusters);
            spinner.stop();
        }, 'json');
}

function showClusters(data)
{
    var table = d3.select('#clusterList');
    var tbody = table.select('tbody');

    if (data.length > 7)
        tbody.style('height', '300px');
    else
        tbody.style('height', (42 * data.length) + 'px');

    var rows = tbody.selectAll('tr')
        .data(data)
        .enter()
        .append('tr')
        .each(function (d, i) { if (i % 2 == 1) d3.select(this).classed('odd', true); });

    rows.append('td')
        .classed('select', true)
        .append('input')
        .attr('type', 'checkbox')
        .property('value', function (d) { return d.cid; })
        .on('change', function () { loadJobs(); });
    rows.append('td')
        .text(function (d) { return d.cid; });
    rows.append('td').classed('textcol', true)
        .text(function (d) { return d.user; });
    rows.append('td').classed('textcol', true)
        .text(function (d) { return d.cmd.substring(0, 18); });
    rows.append('td').classed('textcol', true)
        .text(function (d) { return d.timestamp; });
    rows.append('td')
        .text(function (d) { return d.njobs; });

    setColumnWidths(table, rows, clusterListBodyWidths);
}

var loadJobsBlocked = false;
var jobSearchKeys = {
    'search': 'jobs',
    'clusterIds': [],
    'wallTimeMin': 0,
    'wallTimeMax': 0,
    'cpuTimeMin': 0,
    'cpuTimeMax': 0
};

function loadJobs()
{
    if (loadJobsBlocked) {
        setTimeout(function () { loadJobs(); }, 1000);
        return;
    }

    loadJobsBlocked = true;
    setTimeout(function () { loadJobsBlocked = false; }, 1000);

    var clusterIds = [];

    d3.selectAll('#clusterList tbody input')
        .each(function () {
                if (this.checked)
                    clusterIds.push(parseInt(this.value, 10));
            });

    if (clusterIds.length == 0)
        return;

    clusterIds.sort();

    var keys = {
        'wallTimeMin': parseInt(d3.select('#wallTimeMin').property('value')),
        'wallTimeMax': parseInt(d3.select('#wallTimeMax').property('value')),
        'cpuTimeMin': parseInt(d3.select('#cpuTimeMin').property('value')),
        'cpuTimeMax': parseInt(d3.select('#cpuTimeMax').property('value'))
    };

    for (var k in keys) {
        if (keys[k] != keys[k])
            keys[k] = 0;
    }

    var changed = (clusterIds.length != jobSearchKeys.clusterIds.length);

    if (!changed) {
        for (var k in keys) {
            if (keys[k] != jobSearchKeys[k]) {
                changed = true;
                break;
            }
        }
    }

    if (!changed) {
        for (var x = 0; x != clusterIds.length; ++x) {
            if (clusterIds[x] != jobSearchKeys.clusterIds[x]) {
                changed = true;
                break;
            }
        }
    }

    if (!changed)
        return;

    jobSearchKeys.clusterIds = clusterIds;
    for (var k in keys)
        jobSearchKeys[k] = keys[k];

    d3.select('#jobList tbody').selectAll('tr')
        .remove();

    d3.select('#sites').selectAll('div.site')
        .remove();

    d3.select('#exitcodes').selectAll('div.exitcode')
        .remove();

    var spinner = new Spinner({'scale': 5, 'corners': 0, 'width': 2, 'position': 'absolute'});
    spinner.spin();
    $('#jobView').append($(spinner.el));

    $.ajax({'url': 'search.php', 'data': jobSearchKeys, 'success': function (data, textStatus, jqXHR) {
                setupJobSpecs(data);
                showJobs(data.jobs, 'table');
                narrowJobs();
                spinner.stop();
            }, 'dataType': 'json', 'async': false});
}

function setupJobSpecs(data)
{
    var sitesBox = d3.select('#sites');
    
    var textHeight = parseInt(window.getComputedStyle(sitesBox.node()).fontSize, 10);
    if (data.sites.length > 5) {
        sitesBox.style('height', (textHeight * 6) + 'px');
    }
    else
        sitesBox.style('height', (textHeight * (sites.length + 1)) + 'px');

    var lines = sitesBox.selectAll('div.site')
        .data(data.sites)
        .enter().append('div').classed('site', true);
    
    lines.append('input').attr('type', 'checkbox')
        .property('value', function (s) { return s; })
        .property('checked', true)
        .on('change', function () { narrowJobs(); });

    lines.append('span')
        .text(function (s) { return s; });

    var codesBox = d3.select('#exitcodes');
    
    textHeight = parseInt(window.getComputedStyle(codesBox.node()).fontSize, 10);
    if (data.exitcodes.length > 3) {
        codesBox.style('height', (textHeight * 4) + 'px');
    }
    else
        codesBox.style('height', (textHeight * (data.exitcodes.length + 1)) + 'px');

    var lines = codesBox.selectAll('div.exitcode')
        .data(data.exitcodes)
        .enter().append('div').classed('exitcode', true);
    
    lines.append('input').attr('type', 'checkbox')
        .property('value', function (c) { return c; })
        .property('checked', true)
        .on('change', function () { narrowJobs(); });

    lines.append('span')
        .text(function (c) { return c == null ? '-' : c; });
}    

function showJobs(data, area)
{
    if (area == 'table') {
        var table = d3.select('#jobList');
        var thead = table.select('thead');
        var tbody = table.select('tbody');

        var nSuccess = 0;
        var totalCPUTime = 0;
        var totalWallTime = 0;
        for (var x in data) {
            if (data[x].success == 'Yes')
                nSuccess += 1;
            totalCPUTime += data[x].cputime;
            totalWallTime += data[x].walltime;
        }

        thead.select('th.totalJobs')
            .text(data.length + ' Jobs');
        thead.select('th.totalSuccess')
            .text(nSuccess);
        thead.select('th.totalCPUTime')
            .text(totalCPUTime);
        thead.select('th.totalWallTime')
            .text(totalWallTime);

        var rows = tbody.selectAll('tr')
            .data(data)
            .enter()
            .append('tr');

        rows.append('td')
            .text(function (d) { return d.cid; });
        rows.append('td')
            .text(function (d) { return d.pid; });
        rows.append('td').classed('textcol', true)
            .text(function (d) { return d.user; });
        rows.append('td').classed('textcol', true)
            .text(function (d) { return d.cmd.substring(0, 10); });
        rows.append('td').classed('textcol', true)
            .text(function (d) { return d.matchTime; });
        rows.append('td').classed('textcol', true)
            .text(function (d) { return d.frontend; });
        rows.append('td').classed('textcol', true)
            .text(function (d) { return d.site; });
        rows.append('td').classed('textcol', true)
            .text(function (d) { return d.success; });
        rows.append('td')
            .text(function (d) { return d.cputime; });
        rows.append('td')
            .text(function (d) { return d.walltime; });
        rows.append('td')
            .text(function (d) { return d.exitcode == null ? '-' : d.exitcode; });

        setColumnWidths(table, rows, jobListWidths);
    }
}

function narrowJobs()
{
    var sites = [];
    var success = d3.select('#succeeded').property('value');
    var exitcodes = [];

    d3.select('#sites').selectAll('input')
        .each(function () {
                if (this.checked)
                    sites.push(this.value);
            });

    d3.select('#exitcodes').selectAll('input')
        .each(function () {
                if (this.checked) {
                    var val = parseInt(this.value);
                    if (val != val)
                        exitcodes.push(null);
                    else
                        exitcodes.push(parseInt(this.value, 10));
                }
            });

    d3.select('#jobList').select('tbody').selectAll('tr')
        .each(function (d) {
                if (success != "" && d.success != success) {
                    this.style.display = 'none';
                    return;
                }
                
                var x = 0;
                for (; x != sites.length; ++x) {
                    if (sites[x] == d.site)
                        break;
                }
                if (x == sites.length) {
                    this.style.display = 'none';
                    return;
                }

                x = 0;
                for (; x != exitcodes.length; ++x) {
                    if (exitcodes[x] == d.exitcode)
                        break;
                }
                if (x == exitcodes.length) {
                    this.style.display = 'none';
                    return;
                }

                this.style.display = 'block';
            });
}

function setColumnWidths(table, rows, widths)
{
    var tableWidth = table.node().clientWidth;
    rows.selectAll('th,td').data(widths)
        .style('width', function (d, i) { return (tableWidth * d - (i == widths.length - 1 ? 10 : 11)) + 'px'; });
}
