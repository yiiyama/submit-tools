<?php
/*LOCAL CONFIG*/
$rrdpath = '/var/run/condormon';
$title = 'subMIT current job status';
$columns = array(
                 'Running' => array('T2_US_MIT', 'T3_US_MIT', 'EAPS'),
                 'Idle' => NULL,
                 'Held' => NULL
                 );
/*LOCAL CONFIG*/

$colgroups = array('Running', 'Idle', 'Held');

$ncols = 0;
foreach($colgroups as $g) {
  if (is_null($columns[$g]))
    $ncols += 1;
  else
    $ncols += count($columns[$g]);
}

function lastEntry($rrd) {
  global $rrdpath;
  global $ncols;

  $last = rrd_last($rrdpath . '/' . $rrd);
  $options = array('LAST', sprintf('--start=%d', $last - 1), sprintf('--end=%d', $last - 1));
  $dump = rrd_fetch($rrdpath . '/' . $rrd, $options, count($options));
  if (isset($dump['data']) && count($dump['data']) >= $ncols) {
    $chunks = array_chunk($dump['data'], $ncols);
    $entries = $chunks[0];
  }
  else
    $entries = array_fill(0, $ncols, 0);

  return $entries;
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
$html .= '  background-color:#cccccc;' . "\n";
$html .= '  border:1px solid black;' . "\n";
$html .= '}' . "\n";
$html .= 'td {' . "\n";
$html .= '  border:1px solid black;' . "\n";
$html .= '}' . "\n";
$html .= 'tr.odd {' . "\n";
$html .= '  background-color:#eeeeee;' . "\n";
$html .= '}' . "\n";
$html .= 'tr.even {' . "\n";
$html .= '  background-color:#ffffff;' . "\n";
$html .= '}' . "\n";
$html .= 'td.data {' . "\n";
$html .= '  text-align:right;' . "\n";
$html .= '}' . "\n";
$html .= 'div.graphs {' . "\n";
$html .= '  width:810px;' . "\n";
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
$html .= '      <colgroup>' . "\n";
$html .= '        <col style="width:100px;">' . "\n";
for ($i = 0; $i != $ncols; ++$i)
  $html .= '        <col style="width:80px;">' . "\n";
$html .= '        <col style="width:100px;border-left:2px solid;">' . "\n";
$html .= '      <colgroup>' . "\n";

if ($ncols == 3) {
  // no column groups
  $html .= '      <tr>' . "\n";
  $html .= '        <th>User</th>';
  foreach ($colgroups as $g)
    $html .= '<th>' . $g . '</th>';
  $html .= '<th>Total</th>' . "\n";
  $html .= '      </tr>' . "\n";
}
else {
  $html .= '      <tr>' . "\n";
  $html .= '        <th rowspan="2">User</th>';
  foreach ($colgroups as $g) {
    if (is_null($columns[$g]))
      $html .= '<th rowspan="2">' . $g . '</th>';
    else
      $html .= '<th colspan="' . count($columns[$g]) . '">' . $g . '</th>';
  }
  $html .= '<th rowspan="2">Total</th>' . "\n";
  $html .= '      </tr>' . "\n";
  $html .= '      <tr>' . "\n";
  $html .= '        ';
  foreach ($colgroups as $g) {
    if (!is_null($columns[$g])) {
      foreach ($columns[$g] as $c)
        $html .= '<th>' . $c . '</th>';
    }
  }
  $html .= "\n";
  $html .= '      </tr>' . "\n";
}

$images = '';

$irow = 0;
$colTotal = array_fill(0, $ncols, 0);
$total = 0;
foreach ($rrds as $rrd) {
  $user = str_replace('.rrd', '', $rrd);
  if ($user == 'Total')
    continue;

  $lastEntry = lastEntry($rrd);
  
  $html .= '      <tr class="';
  if ($irow % 2 == 0)
    $html .= 'even';
  else
    $html .= 'odd';
  $html .= '">' . "\n";
  $html .= '        <td><a href="jobs/' . $user . '.txt">' . $user . '</a></td>';
  foreach ($lastEntry as $i => $count) {
    if ($count < 0)
      $count = 0;
    $html .= '<td class="data">' . ((int)$count) . '</td>';
    $colTotal[$i] += $count;
  }
  $userTotal = (int)array_sum($lastEntry);
  if ($userTotal < 0)
    $userTotal = 0;
  $total += $userTotal;
  $html .= '<td class="data" style="border-left-width:2px">' . $userTotal . '</td>' . "\n";
  $html .= '      </tr>' . "\n";

  $images .= '    <div class="graphs">' . "\n";
  $images .= '      <div class="username"><a href="jobs/' . $user . '.txt">' . $user . '</a></div>' . "\n";
  $images .= '      <img src="imgs/' . $user . '_2h.png">' . "\n";
  $images .= '      <img src="imgs/' . $user . '_1d.png">' . "\n";
  $images .= '    </div>' . "\n";

  ++$irow;
}

$images .= '    <div class="graphs">' . "\n";
$images .= '      <div class="username">Total</div>' . "\n";
$images .= '      <img src="imgs/Total_2h.png">' . "\n";
$images .= '      <img src="imgs/Total_1d.png">' . "\n";
$images .= '    </div>' . "\n";

$html .= '      <tr style="border-top-width:2px;">' . "\n";
$html .= '        <td>Total</td>';
foreach ($colTotal as $ct)
  $html .= '<td class="data">' . $ct . '</td>';
$html .= '<td class="data" style="border-left-width:2px">' . $total . '</td>' . "\n";
$html .= '      </tr>' . "\n";

$html .= '    </table>' . "\n";
$html .= $images;
$html .= '  </body>' . "\n";
$html .= '</html>' . "\n";

echo $html;
?>