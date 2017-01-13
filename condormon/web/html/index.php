<?php
$rrdpath = '/var/run/condormon';
$title = 'subMIT current job status';
$rrdcolumns = array('running-t2', 'running-t3', 'running-eaps', 'running-osg', 'running-uscms', 'running-cmsitb', 'idle', 'held');
$titles = array('MIT' => array('T2_US_MIT' => 'running-t2', 'T3_US_MIT' => 'running-t3', 'EAPS' => 'running-eaps'), 'OSG' => 'running-osg', 'USCMS' => 'running-uscms', 'CMSITB' => 'running-cmsitb');

function lastEntry($rrd)
{
  global $rrdpath;
  global $rrdcolumns;

  $ncols = count($rrdcolumns);

  $last = rrd_last($rrdpath . '/' . $rrd);
  $options = array('LAST', sprintf('--start=%d', $last - 1), sprintf('--end=%d', $last - 1));
  $dump = rrd_fetch($rrdpath . '/' . $rrd, $options, count($options));
  if (isset($dump['data']) && count($dump['data']) >= $ncols) {
    $chunks = array_chunk($dump['data'], $ncols);
    $entry = $chunks[0];
  }
  else
    $entry = array_fill(0, $ncols, 0);

  $mapped = array();
  foreach ($entry as $i => $d)
    $mapped[$rrdcolumns[$i]] = $d;

  return $mapped;
}

$rrds = array();

$dirp = opendir($rrdpath);
while (($ent = readdir($dirp)) !== false) {
  if ($ent == "." || $ent == "..")
    continue;

  if (strpos($ent, ".rrd") == strlen($ent) - 4)
    $rrds[] = $ent;
}
closedir($dirp);

$html = '<html>' . "\n";
$html .= '  <head>' . "\n";
$html .= '    <title>' . $title . '</title>' . "\n";
$html .= '    <style>' . "\n";
$html .= 'body {' . "\n";
$html .= '  font-family:helvetica;' . "\n";
$html .= '}' . "\n";
$html .= 'table {' . "\n";
$html .= '  border:1px solid black;' . "\n";
$html .= '  border-collapse:collapse;' . "\n";
$html .= '}' . "\n";
$html .= 'tr {' . "\n";
$html .= '  border:1px solid black;' . "\n";
$html .= '}' . "\n";
$html .= 'th {' . "\n";
$html .= '  width:90px;' . "\n";
$html .= '  background-color:#cccccc;' . "\n";
$html .= '  border:1px solid black;' . "\n";
$html .= '}' . "\n";
$html .= 'td {' . "\n";
$html .= '  width:90px;' . "\n";
$html .= '  border:1px solid black;' . "\n";
$html .= '}' . "\n";
$html .= 'tr.odd {' . "\n";
$html .= '  background-color:#eeeeee;' . "\n";
$html .= '}' . "\n";
$html .= 'tr.even {' . "\n";
$html .= '  background-color:#ffffff;' . "\n";
$html .= '}' . "\n";
$html .= 'tr.total {' . "\n";
$html .= '  border-top:2px solid;' . "\n";
$html .= '}' . "\n";
$html .= 'td {' . "\n";
$html .= '  text-align:right;' . "\n";
$html .= '}' . "\n";
$html .= 'td.user,th.user {' . "\n";
$html .= '  width:100px;' . "\n";
$html .= '  text-align:left;' . "\n";
$html .= '  border-right:2px solid;' . "\n";
$html .= '}' . "\n";
$html .= 'td.total,th.total {' . "\n";
$html .= '  border-left:2px solid;' . "\n";
$html .= '}' . "\n";
$html .= 'div.graphs {' . "\n";
$html .= '  width:1210px;' . "\n";
$html .= '  margin:10px 0 10px 0;' . "\n";
$html .= '}' . "\n";
$html .= 'div.username {' . "\n";
$html .= '  font-size:150%;' . "\n";
$html .= '  font-weight:bold;' . "\n";
$html .= '  text-align:left;' . "\n";
$html .= '  margin-bottom:10px;' . "\n";
$html .= '}' . "\n";
$html .= '    </style>' . "\n";
$html .= '    <meta http-equiv="refresh" content="300">' . "\n";
$html .= '  </head>' . "\n";
$html .= '  <body>' . "\n";
$html .= '    <table>' . "\n";
$html .= '      <tr>' . "\n";

$nrunning = 0;
foreach ($titles as $title => $target) {
  if (is_array($target))
    $nrunning += count($target);
  else
    $nrunning += 1;
}

$html .= '        <th rowspan="3" class="user">User</th><th rowspan="3">Idle</th><th rowspan="3">Held</th><th rowspan="3" style="border-right:none;">Running</th><th colspan="' . $nrunning . '" style="border-left:none;">&nbsp;</th><th rowspan="3" class="total">Total</th>' . "\n";
$html .= '      </tr>' . "\n";
$html .= '      <tr>' . "\n";
$html .= '        ';
foreach ($titles as $title => $target) {
  if (is_array($target))
    $html .= '<th colspan="' . count($target) . '">' . $title . '</th>';
  else
    $html .= '<th rowspan="2">' . $title . '</th>';
}
$html .= "\n";
$html .= '      </tr>' . "\n";
$html .= '      <tr>' . "\n";
$html .= '        ';
foreach ($titles as $title => $target) {
  if (!is_array($target))
    continue;
  foreach ($target as $subtitle => $counter)
    $html .= '<th>' . $subtitle . '</th>';
}
$html .= "\n";
$html .= '      </tr>' . "\n";

$images = '';

$irow = 0;
$colTotal = array();
foreach ($rrdcolumns as $key)
  $colTotal[$key] = 0;

$total = 0;
foreach ($rrds as $rrd) {
  $user = str_replace('.rrd', '', $rrd);
  if ($user == 'Total')
    continue;

  $lastEntry = lastEntry($rrd);

  $userTotal = (int)array_sum($lastEntry);
  if ($userTotal < 0)
    $userTotal = 0;

  $runTotal = $userTotal - $lastEntry['idle'] - $lastEntry['held'];
  if ($runTotal < 0)
    $runTotal = 0;

  $total += $userTotal;

  foreach ($rrdcolumns as $key)
    $colTotal[$key] += $lastEntry[$key];
  
  $html .= '      <tr class="';
  if ($irow % 2 == 0)
    $html .= 'even';
  else
    $html .= 'odd';
  $html .= '">' . "\n";
  $html .= '        <td class="user"><a href="jobs/' . $user . '.txt">' . $user . '</a></td>';
  $html .= '<td>' . $lastEntry['idle'] . '</td>';
  $html .= '<td>' . $lastEntry['held'] . '</td>';
  $html .= '<td>' . $runTotal . '</td>';
  foreach ($rrdcolumns as $key) {
    if (strpos($key, 'running-') === 0)
      $html .= '<td>' . $lastEntry[$key] . '</td>';
  }
  $html .= '<td class="total">' . $userTotal . '</td>' . "\n";
  $html .= '      </tr>' . "\n";

  $images .= '    <div class="graphs">' . "\n";
  $images .= '      <div class="username"><a href="jobs/' . $user . '.txt">' . $user . '</a></div>' . "\n";
  $images .= '      <img src="imgs/' . $user . '_2h.png">' . "\n";
  $images .= '      <img src="imgs/' . $user . '_1d.png">' . "\n";
  $images .= '      <img src="imgs/' . $user . '_1w.png">' . "\n";
  $images .= '    </div>' . "\n";

  ++$irow;
}

$runTotal = $total - $colTotal['idle'] - $colTotal['held'];
if ($runTotal < 0)
  $runTotal = 0;

$html .= '      <tr class="total">' . "\n";
$html .= '        <td class="user">Total</td>';
$html .= '<td>' . $colTotal['idle'] . '</td>';
$html .= '<td>' . $colTotal['held'] . '</td>';
$html .= '<td>' . $runTotal . '</td>';
foreach ($rrdcolumns as $key) {
  if (strpos($key, 'running-') === 0)
    $html .= '<td>' . $colTotal[$key] . '</td>';  
}
$html .= '<td class="total">' . $total . '</td>' . "\n";
$html .= '      </tr>' . "\n";

$images .= '    <div class="graphs">' . "\n";
$images .= '      <div class="username">Total</div>' . "\n";
$images .= '      <img src="imgs/Total_2h.png">' . "\n";
$images .= '      <img src="imgs/Total_1d.png">' . "\n";
$images .= '      <img src="imgs/Total_1w.png">' . "\n";
$images .= '    </div>' . "\n";

$html .= '    </table>' . "\n";
$html .= $images;
$html .= '  </body>' . "\n";
$html .= '</html>' . "\n";

echo $html;
?>