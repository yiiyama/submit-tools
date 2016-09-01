var findClusterBlocked = false;

function findClustersWith(key)
{
    if (findClusterBlocked)
        return;

    findClusterBlocked = true;
    setTimeout(function () { findClusterBlocked = false; }, 500);

    var key = $('#' + key);
    var str = key.val();
    var search = str.split(' ');
    search.sort();
    
    var current = key.data('keys');
    if (current === undefined)
        current = [];

    if (current.length == search.length) {
        var x = 0;
        for (x = 0; x != current.length; ++x) {
            if (search[x] != current[x])
                break;
        }
        if (x == current.length)
            return;
    }

    key.data('keys', search);

    loadClusters();
}

function loadClusters()
{
    var inputData = {
        'search': 'clusters',
        'users': $('#users').data('keys'),
        'cmds': $('#cmds').data('keys')
    };

    $.get('search.php', inputData, function (data, textStatus, jqXHR) {
            showClusters(data);
        }, 'json');
}

function showClusters(data)
{
    var rows = d3.select('#clusterList tbody').selectAll('tr')
        .remove()
        .data(data)
        .enter()
        .append('tr')
        .attr('id', function (d) { return 'cluster' + d.cid; });
        
    rows.append('td')
        .classed('select', true)
        .append('input')
        .attr('type', 'checkbox')
        .on('change', function () { loadJobs(); });
    rows.append('td')
        .classed('clusterId', true)
        .text(function (d) { return d.cid; });
    rows.append('td')
        .text(function (d) { return d.user; });
    rows.append('td')
        .text(function (d) { return d.cmd; });
    rows.append('td')
        .text(function (d) { return d.timestamp; });
    rows.append('td')
        .text(function (d) { return d.njobs; });
}

function loadJobs()
{
    var clusterIds = [];
    d3.selectAll('#clusterList tbody tr')
        .each(function () {
                var thissel = d3.select(this);
                if (thissel.select('.select input').property('checked'))
                    clusterIds.push(0 + thissel.select('.clusterId').text());
            });
    
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
        var rows = d3.selectAll('jobTable tbody tr')
            .remove()
            .data(data)
            .enter()
            .append('tr');

        rows.append('td')
            .text(function (d) { return d.cid; });
        rows.append('td')
            .text(function (d) { return d.pid; });
        rows.append('td')
            .text(function (d) { return d.matchTime; });
        rows.append('td')
            .text(function (d) { return d.success; });
        rows.append('td')
            .text(function (d) { return d.cputime; });
        rows.append('td')
            .text(function (d) { return d.walltime; });
        rows.append('td')
            .text(function (d) { return d.exitcode; });
    }
}
