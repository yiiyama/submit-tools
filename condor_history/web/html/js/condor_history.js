var users = {};
var frontends = {};
var sites = {};
var clusters = {};
var exitcodes = [];
var jobs = [];

var clusterSearchKeys = {
    'search': 'clusters',
    'users': [],
    'cmds': [],
    'ids': [],
    'begin': '',
    'end': ''
};
var jobSearchKeys = {
    'search': 'jobs',
    'users': [],
    'cmds': [],
    'ids': [],
    'begin': '',
    'end': '',
    'clusterIds': []
};

var viewNames = ['siteStats', 'exitCodes', 'dayByDay', 'timeDistribution', 'jobList'];
var viewData = {
    'siteStats': {'title': 'Jobs by Site', 'jsonData': null, 'xorigin': 20., 'nmapping': null, 'tmapping': null},
    'exitCodes': {'title': 'Exit codes', 'jsonData': null, 'xorigin': 10., 'jobMap': {}, 'panelHeight': 50., 'topMargin': 0.1, 'bottomMargin': 0.05, 'xmapping': null, 'ymapping': null},
    'dayByDay': {'title': 'History', 'jsonData': null, 'xorigin': 10., 'jobMap': [], 'xmapping': null, 'ymapping': null, 'panelHeight': 20., 'topMargin': 0.1, 'bottomMargin': 0.1},
    'timeDistribution': {'title': 'CPU and Wall Time Distribution', 'jsonData': null, 'xorigin': 5., 'panelHeight': 50., 'topMargin': 0.1, 'bottomMargin': 0.05, 'xmapping': null},
    'jobList': {'title': 'Table', 'jsonData': null}
};

var exitCodesPerRow = 16;
var sitesPerRow = 4;

String.prototype.strcmp = function (s) {
    if (this < s) return -1;
    if (this > s) return 1;
    return 0;
};

function initPage()
{
    /*
      Collect static data (users and frontends) and fill their maps.
      Set up the interfaces (date picker, cluster table, and job views).
    */

    // Get users

    $.ajax({'url': 'search.php', 'data': {'search': 'initial'}, 'dataType': 'json', 'async': false, 'success': function (data, textStatus, jqXHR) {
            for (var x in data.users)
                users[data.users[x].id] = data.users[x];

            frontends = data.frontends;

            var userRows = d3.select('#users').selectAll('tr')
                .data(data.users)
                .enter()
                .append('tr');

            userRows.append('td')
                .append('input')
                .attr('type', 'checkbox')
                .property('value', function (d) { return d.id; })
                .on('change', function () { findClusters(); });

            userRows.append('td')
                .text(function (d) { return d.name; });
            }});

    d3.select('#allUsers')
        .on('click', function () {
                var select = (this.value == 'Select All');
                if (select)
                    this.value = 'Unselect All';
                else
                    this.value = 'Select All';
                d3.selectAll('#users input').property('checked', select);
                findClusters();
            });

    // Set up cluster search interface

    // somehow selection.on() does not work here (in combination with datepicker?)
    d3.selectAll('#clusterSearch input')
        .each(function () {
                this.onkeyup = function () { findClusters(); };
                this.onchange = function () { findClusters(); }
            });
    
    $.datepicker.setDefaults({'dateFormat': 'yy/mm/dd'});

    var begin = $('#submitBegin');
    begin.datepicker({'defaultDate': -1});
    begin.datepicker('setDate', -1);
    begin.val($.datepicker.formatDate('yy/mm/dd', begin.datepicker('getDate')));
    var end = $('#submitEnd');
    end.datepicker({'defaultDate': new Date()});
    end.datepicker('setDate', new Date());
    end.val($.datepicker.formatDate('yy/mm/dd', end.datepicker('getDate')));

    // Set up the cluster table

    var clusterSelect = d3.select('#clusterSelect');
    d3.select('#clusterListHead')
        .style('width', (clusterSelect.node().clientWidth * 0.96) + 'px');
    d3.select('#clusterList')
        .style('width', (clusterSelect.node().clientWidth * 0.96) + 'px');

    d3.select('#selectAllClusters')
        .on('change', function () {
                var check = d3.selectAll('#clusterList tbody tr td.select input');
                check.property('checked', this.checked);
                loadJobs();
            });

    // Set up static job search interface

    var jobSearchFields = d3.selectAll('#jobSearch div.jobSearchKey');
    jobSearchFields.selectAll('input')
        .on({'keyup': function () { downselect(); updateView(); }, 'change': function () { downselect(); updateView(); }});
    jobSearchFields.selectAll('select')
        .on('change', function () { downselect(); updateView(); });

    // Set up job views

    var views = d3.select('#display').selectAll('article.view')
        .data(viewNames)
        .enter()
        .append('article').classed('view', true)
        .attr('id', function (d) { return d; });

    var viewHeader = views.append('div').classed('viewHeader', true);

    viewHeader.append('div').classed('toggleView clickable', true)
        .html('&#9661; ')
        .on('click', function (d) { toggleView(d); });
        
    viewHeader.append('div').classed('viewTitle', true)
        .text(function (d) { return viewData[d].title; });

    viewHeader.append('div').classed('viewGetData', true)
        .append('input').attr('type', 'button')
        .property('value', 'JSON')
        .property('disabled', true)
        .on('click', function (d) { dumpJSON(d); });

    viewHeader.append('div').classed('viewGetData', true)
        .append('input').attr('type', 'button')
        .property('value', 'CSV')
        .property('disabled', true)
        .on('click', function (d) { dumpCSV(d); });

    views.append('div').classed('viewBody', true)
        .style('display', 'none');
}

var findClusterBlocked = false;

function findClusters()
{
    /*
      Called when one of the cluster search fields changes its value.
      Collect the conditions from search fields and compare to the global clusterSearchKeys.
      If keys changed, empty the table and call showClusters() via ajax.
    */

    if (findClusterBlocked) {
        setTimeout(function () { findClusters(); }, 1000);
        return;
    }

    findClusterBlocked = true;

    var searchKeys = {'users': [], 'cmds': [], 'ids': [], 'begin': '', 'end': ''};

    d3.select('#users').selectAll('input:checked')
        .each(function () {
                searchKeys.users.push(this.value);
            });

    var cmdstr = $.trim(d3.select('#cmds').property('value'));
    if (cmdstr != '') {
        searchKeys.cmds = cmdstr.split(' ');
        searchKeys.cmds.sort();
    }

    var idstr = $.trim(d3.select('#clusterIds').property('value'));
    if (idstr != '') {
        var idstrs = idstr.split(' ');
        for (var x in idstrs) {
            var i = parseInt(idstrs[x]);
            if (i == i)
                searchKeys.ids.push(i);
        }
        searchKeys.ids.sort();
    }

    searchKeys.begin = $.trim(d3.select('#submitBegin').property('value'));
    searchKeys.end = $.trim(d3.select('#submitEnd').property('value'));

    if (!compareData(clusterSearchKeys, searchKeys)) {
        findClusterBlocked = false;
        return;
    }

    d3.select('#clusterList tbody').selectAll('tr')
        .remove();

    var spinner = new Spinner({'scale': 5, 'corners': 0, 'width': 2, 'position': 'fixed', 'top': '30%', 'left': '45%'});
    spinner.spin();
    $('#clusterSelect').append($(spinner.el));

    $.ajax({'url': 'search.php', 'data': clusterSearchKeys, 'dataType': 'json', 'async': false, 'method': 'POST',
                'error': function (jqXHR, textStatus, errorThrown) {
                    d3.select('#ajaxErrorMessage').text(textStatus + '(' + errorThrown + ')');
                    spinner.stop();
                },
                'success': function (data, textStatus, jqXHR) {
                    if (data.many) {
                        allowAggregateOnly(true);
                        loadJobs();
                        spinner.stop();
                    }
                    else {
                        allowAggregateOnly(false);
                        showClusters(data.clusters);
                        clusters = {};
                        for (var x in data.clusters)
                            clusters[data.clusters[x].id] = data.clusters[x];
                        loadJobs();
                        spinner.stop();
                    }
                }});

    findClusterBlocked = false;
}

function allowAggregateOnly(allow)
{
    if (allow) {
        var select = d3.select('#clusterSelect');
        select.selectAll('div.clusterListContainer')
            .style('display', 'none');
        select.select('span.message').remove();
        select.append('span').classed('message', true)
            .text('Too many job clusters to display');

        d3.select('#jobList')
            .style('display', 'none');

        jobSearchKeys.search = 'jobsFromClusters';
    }
    else {
        var select = d3.select('#clusterSelect');
        select.select('span.message')
            .remove();
        select.selectAll('div.clusterListContainer')
            .style('display', 'block');

        d3.select('#jobList')
            .style('display', 'block');

        jobSearchKeys.search = 'jobs';
    }
}

function showClusters(data)
{
    /*
      Display and set up cluster rows.
    */

    var table = d3.select('#clusterList');
    var tbody = table.select('tbody');

    var container = d3.select(table.node().parentNode);

    if (data.length > 7)
        container.style({'height': '300px', 'overflow-y': 'scroll'});
    else
        container.style({'height': (42 * data.length) + 'px', 'overflow-y': 'initial'});

    var rows = tbody.selectAll('tr')
        .data(data)
        .enter()
        .append('tr')
        .each(function (d, i) { if (i % 2 == 1) d3.select(this).classed('odd', true); });

    rows.append('td')
        .classed('select', true)
        .append('input')
        .attr('type', 'checkbox')
        .property('value', function (d) { return d.id; })
        .on('change', function () { loadJobs(); });
    rows.append('td')
        .text(function (d) { return d.id; });
    rows.append('td').classed('textcol', true)
        .text(function (d) { return users[d.user].name; });
    rows.append('td').classed('textcol', true)
        .text(function (d) { return d.cmd.substring(0, 18); });
    rows.append('td').classed('textcol', true)
        .text(function (d) { return d.timestamp; });
    rows.append('td')
        .text(function (d) { return d.njobs; });
}

var loadJobsBlocked = false;

function loadJobs()
{
    /*
      Called when the cluster selection changes.
      Collect the conditions from search fields and compare to the global jobSearchKeys.
      If keys changed, call setupJobSelectors(), attachData(), downselect(), and updateView() via sjax.
    */

    if (loadJobsBlocked) {
        setTimeout(function () { loadJobs(); }, 1000);
        return;
    }

    loadJobsBlocked = true;

    var searchKeys = {};

    if (jobSearchKeys.search == 'jobs') {
        searchKeys.clusterIds = []

        d3.selectAll('#clusterList tbody input:checked')
            .each(function () {
                    searchKeys.clusterIds.push(parseInt(this.value));
                });

        searchKeys.clusterIds.sort();
    }
    else {
        searchKeys.clusterIds = [0]; // allows resetting of job lists
        for (var k in clusterSearchKeys) {
            if (k != 'search')
                searchKeys[k] = clusterSearchKeys[k];
        }
    }

    if (!compareData(jobSearchKeys, searchKeys)) {
        loadJobsBlocked = false;
        return;
    }

    var spinner = new Spinner({'scale': 5, 'corners': 0, 'width': 2, 'position': 'absolute'});
    spinner.spin();
    $('#display').append($(spinner.el));

    $.ajax({'url': 'search.php', 'data': jobSearchKeys, 'dataType': 'json', 'async': false, 'method': 'POST',
                'error': function (jqXHR, textStatus, errorThrown) {
                    d3.select('#ajaxErrorMessage').text(textStatus + '(' + errorThrown + ')');
                    spinner.stop();
                },
                'success': function (data, textStatus, jqXHR) {
                    sites = {};
                    for (var x in data.sites)
                        sites[data.sites[x].id] = data.sites[x];
                    exitcodes = data.exitcodes;

                    setupJobSelectors(data);
                    jobs = data.jobs;
                    attachData();
                    downselect();
                    updateView();
                    spinner.stop();
                }});

    loadJobsBlocked = false;
}

function setupJobSelectors(data)
{
    /*
      Clear and set up selection elements specific to the current set of jobs.
    */

    d3.select('#sites').selectAll('tr')
        .remove();

    d3.select('#exitcodes').selectAll('tr')
        .remove();
    
    var siteRows = d3.select('#sites').selectAll('tr')
        .data(data.sites)
        .enter()
        .append('tr');
    
    siteRows.append('td')
        .append('input')
        .attr('type', 'checkbox')
        .property('value', function (s) { return s.id; })
        .property('checked', true)
        .on('change', function () {
                downselect();
                updateView();
            });

    siteRows.append('td')
        .text(function (s) { return s.name; });

    d3.select('#allSites')
        .property('value', 'Unselect All')
        .on('click', function () {
                var select = (this.value == 'Select All');
                if (select)
                    this.value = 'Unselect All';
                else
                    this.value = 'Select All';
                d3.selectAll('#sites input').property('checked', select);
                downselect();
                updateView();
            });

    var codeRows = d3.select('#exitcodes').selectAll('tr')
        .data(data.exitcodes)
        .enter()
        .append('tr');
    
    codeRows.append('td')
        .append('input')
        .attr('type', 'checkbox')
        .property('value', function (c) {
                if (c == null)
                    return '';
                else
                    return c;
            })
        .property('checked', true)
        .on('change', function () {
                downselect();
                updateView();
            });

    codeRows.append('td')
        .text(function (c) { return c == null ? 'Null' : c; });

    d3.select('#allExitcodes')
        .property('value', 'Unselect All')
        .on('click', function () {
                var select = (this.value == 'Select All');
                if (select)
                    this.value = 'Unselect All';
                else
                    this.value = 'Select All';
                d3.selectAll('#exitcodes input').property('checked', select);
                downselect();
                updateView();
            });
}

function toggleView(id)
{
    /*
      Change visibility of the view. If collapsed, remove contents. If expanded, call setupView().
    */

    var view = d3.select('#' + id);
    var body = view.select('div.viewBody');
    if (body.style('display') == 'none') {
        body.style('display', 'block');
        setupView(id);
        attachData(id);
        updateView(id);

        view.select('div.toggleView')
            .html('&#9651; ');

        view.selectAll('div.viewGetData input')
            .property('disabled', false);
    }
    else {
        body.selectAll('*')
            .remove();
        body.style('display', 'none');

        view.select('div.toggleView')
            .html('&#9661; ');

        view.selectAll('div.viewGetData input')
            .property('disabled', true);
    }
}

function setupView(id)
{
    /*
      Set up the tables, graphs, etc. of the view.
    */

    if (id == 'siteStats') {
        var canvas = d3.select('#siteStats div.viewBody')
            .append('svg');

        canvas.style('width', '100%');

        canvas.append('g').classed('legendArea', true)
            .append('g').classed('legend', true)
            .attr('transform', 'translate(' + viewData.siteStats.xorigin + ',1)')
            .append('text').classed('legendTitle', true);

        canvas.append('g').classed('graphArea', true);
    }
    else if (id == 'exitCodes') {
        var canvas = d3.select('#exitCodes div.viewBody')
            .append('svg');

        canvas.style('width', '100%');

        canvas.append('g').classed('legendArea', true)
            .append('g').classed('legend', true)
            .attr('transform', 'translate(' + viewData.exitCodes.xorigin + ',1)')
            .append('text').classed('legendTitle', true);

        canvas.append('g').classed('graphArea', true);
    }
    else if (id == 'dayByDay') {
        var canvas = d3.select('#dayByDay div.viewBody')
            .append('svg');

        canvas.style('width', '100%');

        canvas.append('g').classed('legendArea', true)
            .append('g').classed('legend', true)
            .attr('transform', 'translate(' + viewData.dayByDay.xorigin + ',1)')
            .append('text').classed('legendTitle', true);

        canvas.append('g').classed('graphArea', true);
    }
    else if (id == 'timeDistribution') {
        var box = d3.select('#timeDistribution div.viewBody')
            .style('height', (viewData.timeDistribution.panelHeight * 2 + 10));
        var canvas = box.append('svg')
            .style('width', '100%')
            .attr('viewBox', '0 0 100 ' + (viewData.timeDistribution.panelHeight * 2 + 10));

        canvas.append('g').classed('legendArea', true)
            .append('g').classed('legend', true)
            .attr('transform', 'translate(' + viewData.siteStats.xorigin + ',1)')
            .append('text').classed('legendTitle', true);

        var graphArea = canvas.append('g').classed('graphArea', true);
        graphArea.append('g').classed('cpuGraph', true)
            .append('text').classed('graphTitle', true)
            .text('CPU Time');
        graphArea.append('g').classed('wallGraph', true)
            .attr('transform', 'translate(0,' + viewData.timeDistribution.panelHeight + ')')
            .append('text').classed('graphTitle', true)
            .text('Wallclock Time');

        graphArea.selectAll('text.graphTitle')
            .attr({'font-size': 2, 'transform': 'translate(3,3)'});
    }
    else if (id == 'jobList') {
        var table = d3.select('#jobList div.viewBody').append('table').classed('selector', true)
            .style({'width': '98%', 'height': '42px'});

        var colWidths = [5, 5, 5, 10, 12, 15, 23, 10, 10, 5];

        table.append('colgroup')
            .selectAll('col')
            .data(colWidths)
            .enter()
            .append('col')
            .style('width', function (d) { return d + '%'; });

        var thead = table.append('thead');
        table.append('tbody');

        var headRow = thead.append('tr');

        headRow.append('th').text('ClusterId');
        headRow.append('th').text('ProcId');
        headRow.append('th').text('User');
        headRow.append('th').text('Executable');
        headRow.append('th').text('Start date');
        headRow.append('th').text('Frontend');
        headRow.append('th').text('Site');
        headRow.append('th').text('CPU time (s)');
        headRow.append('th').text('Wallclock time (s)');
        headRow.append('th').text('Exit code');

        headRow = table.select('thead').append('tr');

        headRow.append('th').text('Total');
        headRow.append('th').classed('totalJobs', true);
        headRow.append('th');
        headRow.append('th');
        headRow.append('th');
        headRow.append('th');
        headRow.append('th');
        headRow.append('th').classed('totalCPUTime', true).style('text-align', 'right');
        headRow.append('th').classed('totalWallTime', true).style('text-align', 'right');
        headRow.append('th');

        headRow.selectAll('th').style({'color': 'black', 'background-color': '#ffffff', 'border-bottom': '1px dashed'});
    }
}

function attachData(id)
{
    /*
      Clear and attach jobs data to view.
    */

    var target = findTargets(id);

    if (target.siteStats) {
        var box = d3.select('#siteStats div.viewBody');
        var canvas = box.select('svg');

        var legend = canvas.select('g.legendArea g.legend');
        exitcodeLegend(legend);

        var graphArea = canvas.select('g.graphArea');

        graphArea.selectAll('g.siteData')
            .remove();
        graphArea.selectAll('g.axis')
            .remove();

        graphArea.attr('transform', 'translate(0,' + (3 * Math.floor(exitcodes.length / exitCodesPerRow) + 2) + ')');

        var totals = {};
        for (var i = 0; i != jobs.length; ++i) {
            var job = jobs[i];
            if (totals[job.site] === undefined)
                totals[job.site] = {'n': 1, 'cpu': job.cputime / 3600., 'wall': job.walltime / 3600.};
            else {
                totals[job.site].n += 1;
                totals[job.site].cpu += job.cputime / 3600.;
                totals[job.site].wall += job.walltime / 3600.;
            }
        }

        var feSites = {};
        var sortedSites = [];
        for (var fid in frontends) {
            feSites[fid] = [];
            for (var sid in sites) {
                var site = sites[sid];
                if (site.frontend == fid)
                    feSites[fid].push(site);
            }
            feSites[fid].sort(function (s1, s2) { return s1.name.strcmp(s2.name); });
            sortedSites = sortedSites.concat(feSites[fid]);
        }

        var maxN = 1;
        var maxC = 1;
        var maxW = 1;
        for (var sid in totals) {
            if (totals[sid].n > maxN)
                maxN = totals[sid].n;
            if (totals[sid].cpu > maxC)
                maxC = totals[sid].cpu;
            if (totals[sid].wall > maxW)
                maxW = totals[sid].wall;
        }

        var ymax = sortedSites.length * 5 + 60;
        var height = box.node().clientWidth * ymax / 100; // clientWidth -> 1 in svg coordinates

        box.style('height', height + 'px');
        // coordinate system: [0, 100] x [0, Nsite*5 + 10]
        canvas.attr('viewBox', '0 0 100 ' + ymax);

        viewData.siteStats.nmapping = d3.scale.linear()
            .domain([0, maxN * 1.05])
            .range([0, 95. - viewData.siteStats.xorigin]);

        var naxis = d3.svg.axis()
            .scale(viewData.siteStats.nmapping)
            .orient('bottom')
            .tickSize(0.6, 1);

        var gnaxis = graphArea.append('g').classed('axis horizontal naxis', true)
            .attr('transform', 'translate(' + viewData.siteStats.xorigin + ',2.5)')
            .call(naxis)
            .append('text').classed('axisTitle', true)
            .attr({'font-size': 0.8, 'text-anchor': 'end', 'dx': '-1em'})
            .text('Jobs');

        viewData.siteStats.tmapping = d3.scale.linear()
            .domain([0, Math.max(maxC, maxW) * 1.05])
            .range([0, 95. - viewData.siteStats.xorigin]);

        var taxis = d3.svg.axis()
            .scale(viewData.siteStats.tmapping)
            .orient('bottom')
            .tickSize(0.6, 0);

        var gtaxis = graphArea.append('g').classed('axis horizontal taxis', true)
            .attr('transform', 'translate(' + viewData.siteStats.xorigin + ',5)')
            .call(taxis)
            .append('text').classed('axisTitle', true)
            .attr({'font-size': 0.8, 'text-anchor': 'end', 'dx': '-1em'})
            .text('Time (h)');

        graphArea.selectAll('g.horizontal').selectAll('g.tick text')
            .attr('y', -1.);

        var ymapping = d3.scale.ordinal()
            .domain(sortedSites.map(function (s) { return s.name; }))
            .rangePoints([0, ymax - 5], 1);

        var yaxis = d3.svg.axis()
            .scale(ymapping)
            .orient('left')
            .tickSize(0, 0);

        var gyaxis = graphArea.append('g').classed('axis yaxis', true)
            .attr('transform', 'translate(' + viewData.siteStats.xorigin + ',5)')
            .call(yaxis)
            .selectAll('g.tick text')
            .attr('x', -3);

        formatAxes(graphArea);

        if (jobs.length == 0)
            return;

        var siteData = graphArea.selectAll('g.siteData')
            .data(sortedSites)
            .enter()
            .append('g').classed('siteData', true)
            .attr('transform', function (d) { return 'translate(' + viewData.siteStats.xorigin + ',' + (5 + ymapping(d.name)) + ')'; });

        siteData.append('g').classed('jobCounts', true)
            .attr('transform', 'translate(0,-1.7)')
            .append('text').classed('barKey', true)
            .attr({'text-anchor': 'end', 'transform': 'translate(-0.3,0.6)'})
            .text('Jobs');
        siteData.append('g').classed('cpuTimes', true)
            .attr('transform', 'translate(0,-0.5)')
            .append('text').classed('barKey', true)
            .attr({'text-anchor': 'end', 'transform': 'translate(-0.3,0.6)'})
            .text('CPU');
        siteData.append('g').classed('wallTimes', true)
            .attr('transform', 'translate(0,0.7)')
            .append('text').classed('barKey', true)
            .attr({'text-anchor': 'end', 'transform': 'translate(-0.3,0.6)'})
            .text('Wall');

        graphArea.selectAll('text.barKey')
            .attr('font-size', 0.6);
    }
    else if (target.exitCodes) {
        var canvas = d3.select('#exitCodes div.viewBody').select('svg');

        var legend = canvas.select('g.legendArea g.legend');

        siteLegend(legend);

        var nLegRows = Math.floor(legend.selectAll('g.legendEntry').size() / sitesPerRow);

        canvas.attr('viewBox', '0 0 100 ' + (viewData.exitCodes.panelHeight + nLegRows * 2 + 5));

        var graphArea = canvas.select('g.graphArea');

        graphArea.attr('transform', 'translate(0,' + (nLegRows * 2 + 5) + ')');

        viewData.exitCodes.jobMap = {}; // {code -> [list of jobs]}

        for (var x in jobs) {
            var job = jobs[x];
            var code = job.exitcode;
            if (!(code in viewData.exitCodes.jobMap))
                viewData.exitCodes.jobMap[code] = [];

            viewData.exitCodes.jobMap[code].push(job);
        }

        var maxN = 0;
        for (var x in viewData.exitCodes.jobMap) {
            var n = viewData.exitCodes.jobMap[x].length;
            if (n > maxN)
                maxN = n;
        }

        var graphHeight = viewData.exitCodes.panelHeight * (1 - viewData.exitCodes.topMargin - viewData.exitCodes.bottomMargin);

        graphArea.selectAll('g.axis')
            .remove();

        viewData.exitCodes.ymapping = d3.scale.linear()
            .domain([0, maxN * 1.05])
            .range([graphHeight, 0]);

        var yaxis = d3.svg.axis()
            .scale(viewData.exitCodes.ymapping)
            .orient('left')
            .tickSize(0.6, 1);

        var gyaxis = graphArea.append('g').classed('axis yaxis', true)
            .attr('transform', 'translate(' + viewData.exitCodes.xorigin + ',' + (viewData.exitCodes.panelHeight * viewData.exitCodes.topMargin) + ')')
            .call(yaxis)
            .append('text').classed('axisTitle', true)
            .attr({'font-size': 0.8, 'text-anchor': 'end', 'dx': '-1em'})
            .text('Number of jobs');

        var sortedCodes = d3.keys(viewData.exitCodes.jobMap);
        sortedCodes.sort();

        var xmapping = d3.scale.ordinal()
            .domain(sortedCodes)
            .rangePoints([0., (100 - viewData.exitCodes.xorigin - 5)], 1.);

        var xaxis = d3.svg.axis()
            .scale(xmapping)
            .orient('bottom')
            .tickValues(xmapping.domain())
            .tickSize(0.6, 1);

        var gxaxis = graphArea.append('g').classed('axis xaxis', true)
            .attr('transform', 'translate(' + viewData.exitCodes.xorigin + ',' + (viewData.exitCodes.panelHeight * (1 - viewData.exitCodes.bottomMargin)) + ')')
            .call(xaxis);

        formatAxes(graphArea);

        var binw = (95 - viewData.exitCodes.xorigin) / (sortedCodes.length + 1); // +1 for padding

        gxaxis.selectAll('g.tick text')
            .attr({'x': 0., 'y': 1.8, 'dy': 0});

        graphArea.selectAll('g.codeData').remove();
        var codeData = graphArea.selectAll('g.codeData')
            .data(sortedCodes)
            .enter()
            .append('g').classed('codeData', true)
            .attr('transform', function (d) { return 'translate(' + (viewData.exitCodes.xorigin + xmapping(d) - 0.5 * binw) + ',' + (viewData.exitCodes.panelHeight * (1 - viewData.exitCodes.bottomMargin)) + ')'; });
    }
    else if (target.dayByDay) {
        var canvas = d3.select('#dayByDay div.viewBody').select('svg');

        var legend = canvas.select('g.legendArea g.legend');

        siteLegend(legend);

        var nLegRows = Math.floor(legend.selectAll('g.legendEntry').size() / sitesPerRow);

        canvas.attr('viewBox', '0 0 100 ' + (viewData.dayByDay.panelHeight + nLegRows * 2 + 5));

        var graphArea = canvas.select('g.graphArea');

        graphArea.attr('transform', 'translate(0,' + (nLegRows * 2 + 5) + ')');

        var begin = new Date(d3.select('#submitBegin').property('value'));
        var end = d3.time.day.offset(new Date(d3.select('#submitEnd').property('value')), 1);
        var days = d3.time.day.range(begin, end);

        viewData.dayByDay.jobMap = []; // [[jobs in day 0], [jobs in day 1], ...]
        for (var x in days)
            viewData.dayByDay.jobMap.push([]);

        for (var x in jobs) {
            var job = jobs[x];
            var jobDate = new Date(job.matchTime.replace('-', '/').replace('-', '/'));
            var iD = Math.floor((jobDate - begin) / 1000 / 60 / 60 / 24);
            if (iD >= days.length)
                iD = days.length - 1;
            viewData.dayByDay.jobMap[iD].push(job);
        }

        var maxT = 0;
        for (var x in viewData.dayByDay.jobMap) {
            var dayJobs = viewData.dayByDay.jobMap[x];
            var sum = 0;
            for (var y in dayJobs)
                sum += dayJobs[y].cputime / 3600.;
            if (sum > maxT)
                maxT = sum;
        }

        var graphHeight = viewData.dayByDay.panelHeight * (1 - viewData.dayByDay.topMargin - viewData.dayByDay.bottomMargin);

        graphArea.selectAll('g.axis')
            .remove();

        viewData.dayByDay.ymapping = d3.scale.linear()
            .domain([0, maxT * 1.05])
            .range([graphHeight, 0]);

        var yaxis = d3.svg.axis()
            .scale(viewData.dayByDay.ymapping)
            .orient('left')
            .tickSize(0.6, 1);

        var gyaxis = graphArea.append('g').classed('axis yaxis', true)
            .attr('transform', 'translate(' + viewData.dayByDay.xorigin + ',' + (viewData.dayByDay.panelHeight * viewData.dayByDay.topMargin) + ')')
            .call(yaxis)
            .append('text').classed('axisTitle', true)
            .attr({'font-size': 0.8, 'text-anchor': 'end', 'dx': '-1em'})
            .text('CPU hours');

        var xmapping = d3.time.scale()
            .domain([begin, end])
            .range([0., (100 - viewData.dayByDay.xorigin - 5)]);
       
        var xaxis = d3.svg.axis()
            .scale(xmapping)
            .orient('bottom')
            .ticks(d3.time.day)
            .tickSize(0.6, 1);

        var gxaxis = graphArea.append('g').classed('axis xaxis', true)
            .attr('transform', 'translate(' + viewData.dayByDay.xorigin + ',' + (viewData.dayByDay.panelHeight * (1 - viewData.dayByDay.bottomMargin)) + ')')
            .call(xaxis);

        formatAxes(graphArea);

        var dayw = (95 - viewData.dayByDay.xorigin) / days.length;

        gxaxis.selectAll('g.tick text')
            .attr({'x': 0.45 * dayw, 'y': 1.8, 'dy': 0});

        graphArea.selectAll('g.dayData').remove();
        var dayData = graphArea.selectAll('g.dayData')
            .data(days)
            .enter()
            .append('g').classed('dayData', true)
            .attr('transform', function (d) { return 'translate(' + (viewData.dayByDay.xorigin + xmapping(d)) + ',' + (viewData.dayByDay.panelHeight * (1 - viewData.dayByDay.bottomMargin)) + ')'; });
    }
    else if (target.timeDistribution) {
        var canvas = d3.select('#timeDistribution div.viewBody').select('svg');

        var legend = canvas.select('g.legendArea g.legend')

        exitcodeLegend(legend);

        var graphArea = canvas.select('g.graphArea');

        graphArea.attr('transform', 'translate(0,' + (3 * Math.floor(exitcodes.length / exitCodesPerRow) + 2) + ')');

        var maxCPUJob = d3.max(jobs, function (j) { return j.cputime; });
        var maxWallJob = d3.max(jobs, function (j) { return j.walltime; });

        var xmax = Math.max(maxCPUJob, maxWallJob);

        viewData.timeDistribution.xmapping = d3.scale.linear()
            .domain([0, xmax * 1.05])
            .range([0, 95. - viewData.timeDistribution.xorigin]);

        var xaxis = d3.svg.axis()
            .scale(viewData.timeDistribution.xmapping)
            .orient('bottom')
            .tickSize(0.6, 0);

        var graphHeight = viewData.timeDistribution.panelHeight * (1 - viewData.timeDistribution.topMargin - viewData.timeDistribution.bottomMargin);

        var timeTypes = ['cpu', 'wall'];
        for (var t in timeTypes) {
            var timeType = timeTypes[t];
            var graph = graphArea.select('g.' + timeType + 'Graph');

            graph.selectAll('g.axis')
                .remove();
            graph.select('g.histogram')
                .remove();

            var gxaxis = graph.append('g').classed('axis xaxis', true)
                .attr('transform', 'translate(' + viewData.timeDistribution.xorigin + ',' + (viewData.timeDistribution.panelHeight * (1 - viewData.timeDistribution.bottomMargin)) + ')')
                .call(xaxis);

            gxaxis.selectAll('g.tick text')
                .attr('y', 1);

            gxaxis.append('text').classed('axisTitle', true)
                .attr({'transform': 'translate(90,2)', 'font-size': 1, 'text-anchor': 'end', 'dx': '-1em'})
                .text('Time (s)');

            graph.append('g').classed('axis yaxis', true)
                .attr('transform', 'translate(' + viewData.timeDistribution.xorigin + ',' + (viewData.timeDistribution.panelHeight * viewData.timeDistribution.topMargin) + ')')
                .append('path').classed('domain', true)
                .attr('d', 'M-1,0H0V42.5H-1');

            formatAxes(graph);
        }
    }
    else if (target.jobList) {
        var table = d3.select('#jobList div.viewBody').select('table');
        var tbody = table.select('tbody');
        tbody.selectAll('tr')
            .remove();

        if (jobs.length == 0)
            return;

        var rows = table.select('tbody').selectAll('tr')
            .data(jobs)
            .enter()
            .append('tr');

        rows.append('td')
            .text(function (d) { return d.cid; });
        rows.append('td')
            .text(function (d) { return d.pid; });
        rows.append('td').classed('textcol', true)
            .text(function (d) { return users[clusters[d.cid].user].name; });
        rows.append('td').classed('textcol', true)
            .text(function (d) { return clusters[d.cid].cmd.substring(0, 10); });
        rows.append('td').classed('textcol', true)
            .text(function (d) { return d.matchTime; });
        rows.append('td').classed('textcol', true)
            .text(function (d) { return frontends[sites[d.site].frontend].name; });
        rows.append('td').classed('textcol', true)
            .text(function (d) { return sites[d.site].name; });
        rows.append('td')
            .text(function (d) { return d.cputime; });
        rows.append('td')
            .text(function (d) { return d.walltime; });
        rows.append('td')
            .text(function (d) { return d.exitcode == null ? 'Null' : d.exitcode; });
    }
}

var downselectBlocked = false;

function downselect()
{
    /*
      Set "selected" flag of jobs data according to the given selection.
    */

    if (downselectBlocked) {
        setTimeout(function () { downselect(); }, 1000);
        return;
    }

    downselectBlocked = true;

    var wallTimeMin = parseInt(d3.select('#wallTimeMin').property('value'));
    if (wallTimeMin != wallTimeMin)
        wallTimeMin = 0;
    var wallTimeMax = parseInt(d3.select('#wallTimeMax').property('value'));
    if (wallTimeMax != wallTimeMax)
        wallTimeMax = 0;
    var cpuTimeMin = parseInt(d3.select('#cpuTimeMin').property('value'));
    if (cpuTimeMin != cpuTimeMin)
        cpuTimeMin = 0;
    var cpuTimeMax = parseInt(d3.select('#cpuTimeMax').property('value'));
    if (cpuTimeMax != cpuTimeMax)
        cpuTimeMax = 0;
    var selectedSites = d3.set();
    var selectedCodes = d3.set();

    d3.select('#sites').selectAll('input:checked')
        .each(function () {
                selectedSites.add(this.value);
            });

    d3.select('#exitcodes').selectAll('input:checked')
        .each(function () {
                var val = this.value;
                if (val == "")
                    selectedCodes.add(null);
                else
                    selectedCodes.add(val);
            });

    var m = d3.map(jobs);
    m.forEach(function (i, job) {
            job.selected =
                (wallTimeMin == 0 || job.walltime >= wallTimeMin) &&
                (wallTimeMax == 0 || job.walltime <= wallTimeMax) &&
                (cpuTimeMin == 0 || job.cputime >= cpuTimeMin) &&
                (cpuTimeMax == 0 || job.cputime <= cpuTimeMax) &&
                selectedSites.has(job.site) &&
                selectedCodes.has(job.exitcode);
        });

    downselectBlocked = false;
}

function updateView(id)
{
    /*
      Update views taking the "selected" flag into account.
    */

    if (jobs.length == 0)
        return;

    var target = findTargets(id);

    if (target.siteStats) {
        var canvas = d3.select('#siteStats div.viewBody').select('svg');
        var graphArea = canvas.select('g.graphArea');

        var siteData = graphArea.selectAll('g.siteData');

        for (var sid in sites) {
            var site = sites[sid];
            site.code = {};
            for (var x in exitcodes)
                site.code[exitcodes[x]] = {'n': 0, 'cputime': 0, 'walltime': 0};
        }

        for (var x in jobs) {
            var job = jobs[x];
            if (!job.selected)
                continue;

            var site = sites[job.site];
            site.code[job.exitcode].n += 1;
            site.code[job.exitcode].cputime += job.cputime / 3600.;
            site.code[job.exitcode].walltime += job.walltime / 3600.;
        }

        var ncumul = {};
        var ccumul = {};
        var wcumul = {};

        for (var sid in sites) {
            ncumul[sid] = [0];
            ccumul[sid] = [0];
            wcumul[sid] = [0];
            for (var x = 1; x != exitcodes.length; ++x) {
                var prev = sites[sid].code[exitcodes[x - 1]];
                ncumul[sid].push(ncumul[sid][x - 1] + prev.n);
                ccumul[sid].push(ccumul[sid][x - 1] + prev.cputime);
                wcumul[sid].push(wcumul[sid][x - 1] + prev.walltime);
            }
        }

        var jobBars = siteData.selectAll('g.jobCounts');
        var cpuBars = siteData.selectAll('g.cpuTimes');
        var wallBars = siteData.selectAll('g.wallTimes');

        jobBars.selectAll('rect.bar')
            .remove();
        cpuBars.selectAll('rect.bar')
            .remove();
        wallBars.selectAll('rect.bar')
            .remove();

        viewData.siteStats.jsonData = siteData.data();

        for (var x in exitcodes) {
            var code = exitcodes[x];
            var color = code == null ? '#333333' : colors[code % NCOLORS];

            jobBars.append('rect').classed('bar', true)
                .attr('width', function (s) { return viewData.siteStats.nmapping(s.code[code].n); })
                .attr('transform', function (s) { return 'translate(' + viewData.siteStats.nmapping(ncumul[s.id][x]) + ',0)'})
                .attr('fill', color);

            cpuBars.append('rect').classed('bar', true)
                .attr('width', function (s) { return viewData.siteStats.tmapping(s.code[code].cputime); })
                .attr('transform', function (s) { return 'translate(' + viewData.siteStats.tmapping(ccumul[s.id][x]) + ',0)'})
                .attr('fill', color);

            wallBars.append('rect').classed('bar', true)
                .attr('width', function (s) { return viewData.siteStats.tmapping(s.code[code].walltime); })
                .attr('transform', function (s) { return 'translate(' + viewData.siteStats.tmapping(wcumul[s.id][x]) + ',0)'})
                .attr('fill', color);
        }

        graphArea.selectAll('rect.bar')
            .attr('height', 1);
    }
    else if (target.exitCodes) {
        var canvas = d3.select('#exitCodes div.viewBody').select('svg');
        var graphArea = canvas.select('g.graphArea');

        var codeData = graphArea.selectAll('g.codeData');

        var binw = (95 - viewData.exitCodes.xorigin) / (codeData.size() + 1); // +1 for padding
        var graphHeight = viewData.exitCodes.panelHeight * (1 - viewData.exitCodes.topMargin - viewData.exitCodes.bottomMargin);

        var sortedSites = d3.keys(sites).sort();

        viewData.exitCodes.jsonData = [];

        codeData.each(function (code, icode) {
                var njobs = {};
                for (var s in sites)
                    njobs[s] = 0;

                for (var x in viewData.exitCodes.jobMap[code]) {
                    var job = viewData.exitCodes.jobMap[code][x];
                    if (!job.selected)
                        continue;

                    njobs[job.site] += 1;
                }

                var njobsarr = [];
                for (var x in sortedSites)
                    njobsarr.push(njobs[sortedSites[x]]);

                var totals = [0];
                for (var x in njobsarr) {
                    var prev = totals[x];
                    totals.push(prev + njobsarr[x]);
                }
                totals.shift();

                d3.select(this).selectAll('rect.bar')
                    .data(njobsarr)
                    .enter()
                    .append('rect').classed('bar', true)
                    .attr('width', binw * 0.9)
                    .attr('height', function (d) { return (graphHeight - viewData.exitCodes.ymapping(d)); })
                    .attr('transform', function (d, isite) { return 'translate(' + (binw * 0.05) + ',' + (viewData.exitCodes.ymapping(totals[isite]) - graphHeight) + ')'})
                    .attr('fill', function (d, isite) { return colors[isite % NCOLORS]; });

                var datum = {'code': code, 'sites': []};
                for (var x in sortedSites)
                    datum.sites.push({'name': sites[sortedSites[x]].name, 'njobs': njobsarr[x]});

                viewData.exitCodes.jsonData.push(datum);
            });
    }
    else if (target.dayByDay) {
        var canvas = d3.select('#dayByDay div.viewBody').select('svg');
        var graphArea = canvas.select('g.graphArea');

        var dayData = graphArea.selectAll('g.dayData');

        var dayw = (95 - viewData.dayByDay.xorigin) / dayData.size();
        var graphHeight = viewData.dayByDay.panelHeight * (1 - viewData.dayByDay.topMargin - viewData.dayByDay.bottomMargin);

        var sortedSites = d3.keys(sites).sort();

        viewData.dayByDay.jsonData = [];
        var dateFormat = d3.time.format('%Y-%m-%d');

        dayData.each(function (d, iday) {
                var njobs = {};
                var cputimes = {};
                for (var s in sites) {
                    njobs[s] = 0;
                    cputimes[s] = 0.;
                }

                for (var x in viewData.dayByDay.jobMap[iday]) {
                    var job = viewData.dayByDay.jobMap[iday][x];
                    if (!job.selected)
                        continue;

                    njobs[job.site] += 1;
                    cputimes[job.site] += job.cputime / 3600.;
                }

                var njobsarr = [];
                var cputimesarr = [];
                for (var x in sortedSites) {
                    njobsarr.push(njobs[sortedSites[x]]);
                    cputimesarr.push(cputimes[sortedSites[x]]);
                }

                var totals = [0];
                for (var x in cputimesarr) {
                    var prev = totals[x];
                    totals.push(prev + cputimesarr[x]);
                }
                totals.shift();

                d3.select(this).selectAll('rect.bar')
                    .data(cputimesarr)
                    .enter()
                    .append('rect').classed('bar', true)
                    .attr('width', dayw * 0.9)
                    .attr('height', function (d) { return (graphHeight - viewData.dayByDay.ymapping(d)); })
                    .attr('transform', function (d, isite) { return 'translate(' + (dayw * 0.05) + ',' + (viewData.dayByDay.ymapping(totals[isite]) - graphHeight) + ')'})
                    .attr('fill', function (d, isite) { return colors[isite % NCOLORS]; });

                var datum = {'day': dateFormat(d), 'sites': []};
                for (var x in sortedSites)
                    datum.sites.push({'name': sites[sortedSites[x]].name, 'njobs': njobsarr[x], 'cputime': cputimesarr[x]});

                viewData.dayByDay.jsonData.push(datum);
            });
    }
    else if (target.timeDistribution) {
        var canvas = d3.select('#timeDistribution div.viewBody').select('svg');
        var graphArea = canvas.select('g.graphArea');

        var binning = viewData.timeDistribution.xmapping.ticks(50);
        var xwidth = viewData.timeDistribution.xmapping(binning[1] - binning[0]);
        
        var yorigin = viewData.timeDistribution.panelHeight * (1 - viewData.timeDistribution.bottomMargin);
        var graphHeight = viewData.timeDistribution.panelHeight * (1 - viewData.timeDistribution.topMargin - viewData.timeDistribution.bottomMargin);

        viewData.timeDistribution.jsonData = {};

        var timeTypes = ['cpu', 'wall'];
        for (var t in timeTypes) {
            var timeType = timeTypes[t];
            var graph = graphArea.select('g.' + timeType + 'Graph');

            var totals = [];
            var histData = {};
            for (var x in exitcodes) {
                var code = exitcodes[x];
                histData[code] = [];
                for (var i = 0; i != binning.length - 1; ++i)
                    histData[code].push(0);
            }
            for (var i = 0; i != binning.length - 1; ++i)
                totals.push(0);

            for (var x in jobs) {
                var job = jobs[x];
                if (!job.selected)
                    continue;
            
                var t = job[timeType + 'time'];
                if (t < binning[0] || t >= binning[binning.length - 1])
                    continue;

                var bin = d3.bisect(binning, t);
                histData[job.exitcode][bin] += 1;
                totals[bin] += 1;
            }

            graph.select('g.histogram')
                .remove();
            graph.select('g.yaxis')
                .remove();

            var ymax = d3.max(totals);

            var yaxisMapping = d3.scale.linear()
                .domain([0, ymax * 1.05])
                .range([graphHeight, 0]);

            var yaxis = d3.svg.axis()
                .scale(yaxisMapping)
                .orient('left')
                .tickSize(0.6, 1);

            var gyaxis = graph.append('g').classed('axis yaxis', true)
                .attr('transform', 'translate(' + viewData.timeDistribution.xorigin + ',' + (viewData.timeDistribution.panelHeight * viewData.timeDistribution.topMargin) + ')')
                .call(yaxis);

            formatAxes(graph);

            gyaxis.selectAll('g.tick text')
                .attr('x', -1);

            var histogram = graph.append('g').classed('histogram', true)
                .attr('transform', 'translate(' + viewData.timeDistribution.xorigin + ',' + yorigin + ')');

            var ymapping = d3.scale.linear()
                .domain([0, ymax * 1.05])
                .range([0, graphHeight]);

            for (var i = 0; i != binning.length - 1; ++i)
                totals[i] = 0;

            for (var x in exitcodes) {
                var code = exitcodes[x];

                for (var i = 0; i != binning.length - 1; ++i)
                    totals[i] += histData[code][i];

                var bins = histogram.append('g').classed('codebins', true);
                bins.selectAll('g.bin')
                    .data(histData[code])
                    .enter()
                    .append('g').classed('bin', true)
                    .attr('transform', function (d, i) { return 'translate(' + (xwidth * i) + ',' + -ymapping(totals[i]) + ')'; })
                    .append('rect').classed('bar', true)
                    .attr({'width': xwidth, 'fill': colors[code % NCOLORS]})
                    .attr('height', function (d) { return ymapping(d); });
            }

            viewData.timeDistribution.jsonData[timeType] = [];
            for (var i in binning)
                viewData.timeDistribution.jsonData[timeType].push({});

            for (var x in exitcodes) {
                var code = exitcodes[x];
                for (var i in binning)
                    viewData.timeDistribution.jsonData[timeType][i][code] = histData[code][i];
            }
        }
    }
    else if (target.jobList) {
        var table = d3.select('#jobList table');

        var nJobs = 0;
        var totalCPUTime = 0;
        var totalWallTime = 0;

        table.select('tbody').selectAll('tr')
            .each(function (d) {
                    if (d.selected) {
                        this.style.display = 'table-row';

                        ++nJobs;
                        totalCPUTime += d.cputime;
                        totalWallTime += d.walltime;
                    }
                    else
                        this.style.display = 'none';
                });

        var thead = table.select('thead');

        thead.select('th.totalJobs')
            .text(nJobs + ' Jobs');
        thead.select('th.totalCPUTime')
            .text(totalCPUTime);
        thead.select('th.totalWallTime')
            .text(totalWallTime);

        viewData.jobList.jsonData = [];
        for (x in jobs) {
            if (jobs[x].selected)
                viewData.jobList.jsonData.push(jobs[x]);
        }
    }
}

function setColumnWidths(table, rows, widths)
{
    var tableWidth = table.node().clientWidth;
    rows.selectAll('th,td').data(widths)
        .style('width', function (d, i) { return (tableWidth * d - (i == widths.length - 1 ? 10 : 11)) + 'px'; });
}

function addToBox(box, data, nMax, lineClass)
{
    var textH = parseInt(window.getComputedStyle(box.node()).fontSize);
    if (data.length > nMax) {
        box.style('height', (textH * (nMax + 1)) + 'px');
    }
    else
        box.style('height', (textH * (data.length + 1)) + 'px');

    var lines = box.selectAll('div.' + lineClass)
        .data(data)
        .enter()
        .append('div').classed(lineClass, true);
    
    return lines;
}

function compareData(orig, comp)
{
    var changed = false;

    for (var key in comp) {
        if (Array.isArray(orig[key])) {
            if (orig[key].length == comp[key].length) {
                var x = 0;
                for (x = 0; x != orig[key].length; ++x) {
                    if (comp[key][x] != orig[key][x])
                        break;
                }
                if (x == orig[key].length)
                    continue;
            }
        }
        else if (orig[key] == comp[key])
            continue;

        changed = true;
        break;
    }

    if (changed) {
        for (var key in comp)
            orig[key] = comp[key];
    }

    return changed;
}

function findTargets(id)
{
    var target = {};
    if (id !== undefined) {
        for (var x in viewNames)
            target[viewNames[x]] = false;
        target[id] = true;
    }
    else {
        for (var x in viewNames)
            target[viewNames[x]] = (d3.select('#' + viewNames[x] + ' div.viewBody').style('display') == 'block');
    }

    return target;
}

function formatAxes(graph)
{
    var axes = graph.selectAll('g.axis');

    axes.selectAll('g.tick text')
        .attr('font-size', 0.8);

    axes.select('path.domain')
        .attr({'fill': 'none', 'stroke': 'black', 'stroke-width': 0.1});

    axes.selectAll('g.tick line')
        .attr({'stroke': 'black', 'stroke-width': 0.05});
}

function exitcodeLegend(legend)
{
    legend.select('text.legendTitle')
        .attr({'font-size': 1.6, 'dy': '0.8em', 'x': -0.5, 'y': 0, 'text-anchor': 'end'})
        .text('Exit codes:');

    legend.selectAll('g.legendEntry')
        .remove();

    var legendEntries = legend.selectAll('g.legendEntry')
        .data(exitcodes)
        .enter()
        .append('g').classed('legendEntry', true)
        .attr('transform', function (d, i) { return 'translate(' + ((i % exitCodesPerRow) * 5 + 2) + ',' + (Math.floor(i / exitCodesPerRow) * 2) + ')'; });

    legendEntries.append('rect').classed('legendColor', true)
        .attr({'width': 1.6, 'height': 1.6})
        .attr('fill', function (d) { return d === null ? '#333333' : colors[d % NCOLORS]; });

    legendEntries.append('text').classed('legendText', true)
        .attr({'transform': 'translate(1.8,0)', 'font-size': 1.6, 'dy': '0.8em'})
        .text(function (d) { return d === null ? 'Null' : d; });
}

function siteLegend(legend)
{
    legend.select('text.legendTitle')
        .attr({'font-size': 0.8, 'dy': '0.8em', 'x': -0.5, 'y': 0, 'text-anchor': 'end'})
        .text('Sites:');

    legend.selectAll('g.legendEntry')
        .remove();

    var legendEntries = legend.selectAll('g.legendEntry')
        .data(d3.values(sites))
        .enter()
        .append('g').classed('legendEntry', true)
        .attr('transform', function (d, i) { return 'translate(' + ((i % sitesPerRow) * 20 + 2) + ',' + (Math.floor(i / sitesPerRow) * 2) + ')'; });

    legendEntries.append('rect').classed('legendColor', true)
        .attr({'width': 1.6, 'height': 1.6})
        .attr('fill', function (d, i) { return colors[i % NCOLORS]; });

    legendEntries.append('text').classed('legendText', true)
        .attr({'transform': 'translate(1.8,0)', 'font-size': 0.8, 'dy': '0.8em'})
        .text(function (d) { return d.name; });
}

function dumpJSON(viewName)
{
    var data = encodeURIComponent(JSON.stringify(viewData[viewName].jsonData));
    var dl = document.getElementById('downloadData');
    dl.setAttribute('href', 'data:text/json;charset=utf-8,' + data);
    dl.setAttribute('download', viewName + '.json');
    dl.click();
}

function dumpCSV(viewName)
{
    var csv = '';
    if (viewName == 'siteStats') {
        csv += '"id","name","frontend",';
        for (var x in exitcodes) {
            var code = exitcodes[x];
            csv += '"' + code + ' njobs","' + code + ' CPU time","' + code + ' wall time",';
        }
        csv += "\n";

        for (var x in viewData.siteStats.jsonData) {
            var site = viewData.siteStats.jsonData[x];
            csv += site.id + ',"' + site.name + '",' + site.frontend + ',';
            for (var i in exitcodes) {
                var data = site['code'][exitcodes[i]];
                csv += data['n'] + ',' + data['cputime'] + ',' + data['walltime'] + ',';
            }
        }
    }
    else if (viewName == 'exitCodes') {
        csv += '"site",';
        for (var x in viewData.exitCodes.jsonData) {
            var data = viewData.exitCodes.jsonData[x];
            csv += '"' + data['code'] + ' njobs"';
        }
        csv += '\n';

        var sortedSites = d3.keys(sites).sort();
        for (var s in sortedSites) {
            var sid = sortedSites[s];
            var site = sites[sid];
            csv += '"' + site.name + '",';

            for (var x in viewData.exitCodes.jsonData) {
                var data = viewData.exitCodes.jsonData[x];
                for (var q in data['sites']) {
                    if (data['sites'][q]['name'] != sites[sid].name)
                        continue;
                    csv += data['sites'][q]['njobs'] + ',';
                }
            }
            csv += '\n';
        }
    }
    else if (viewName == 'dayByDay') {
        csv += '"site",';
        for (var x in viewData.dayByDay.jsonData) {
            var data = viewData.dayByDay.jsonData[x];
            csv += '"' + data['day'] + ' njobs","' + data['day'] + ' CPU time",';
        }
        csv += '\n';

        var sortedSites = d3.keys(sites).sort();
        for (var s in sortedSites) {
            var sid = sortedSites[s];
            var site = sites[sid];
            csv += '"' + site.name + '",';

            for (var x in viewData.dayByDay.jsonData) {
                var data = viewData.dayByDay.jsonData[x];
                for (var q in data['sites']) {
                    if (data['sites'][q]['name'] != sites[sid].name)
                        continue;
                    csv += data['sites'][q]['njobs'] + ',' + data['sites'][q]['cputime'] + ',';
                }
            }
            csv += '\n';
        }
    }
    else if (viewName == 'timeDistribution') {
    }
    else if (viewName == 'jobList') {
    }

    var data = encodeURIComponent(csv);
    var dl = document.getElementById('downloadData');
    dl.setAttribute('href', 'data:text/csv;charset=utf-8,' + data);
    dl.setAttribute('download', viewName + '.csv');
    dl.click();
}
