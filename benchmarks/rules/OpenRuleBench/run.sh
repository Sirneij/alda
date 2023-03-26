#!/bin/bash

# run this script in examples/OpenRuleBench

# run everything
daPgms="TCraw DBLPraw Wineraw TC TCrev DBLP Wine_break"
xsbPgms="TCxsb TCWxsb TCrevxsb TCrevWxsb DBLPxsb DBLPWxsb Winexsb WineWxsb"
tcMin=10000
tcMax=100000
# allowed values of cyc: true, false, both.  determines which TC datasets are used.
cyc="both"
startIter=0
endIter=4

tcdatasets=""
for i in $(seq $tcMin 10000 $tcMax); do
    if [ "$cyc" == "true" -o "$cyc" == "both" ]; then
        tcdatasets="${tcdatasets} tc_d1000_par${i}_xsb_cyc.P"
    else
        tcdatasets="${tcdatasets} tc_d1000_par${i}_xsb_nocyc.P"
    fi
done
# remove leading space
tcdatasets="${tcdatasets:1}"
if [ "$cyc" == "both" ]; then
    for i in $(seq $tcMin 10000 $tcMax); do
        tcdatasets="${tcdatasets} tc_d1000_par${i}_xsb_nocyc.P"
    done
fi

if [ ! -d "out" ]; then
    mkdir out
fi

for pgm in ${daPgms}; do
    if [ "${pgm::2}" = "TC" ]; then
        datasets="$tcdatasets"
    elif [ "$pgm" = "DBLPraw" -o "$pgm" = "DBLP" ]; then
        datasets="dblp"
    elif [ "$pgm" = "Wineraw" -o "$pgm" = "Wine_break" ]; then
        datasets="wine"
    else
        echo "unknown program $pgm"
        break
    fi
    for data in ${datasets}; do
        for ((i=${startIter};i<=${endIter};i++)); do
            outfile=out/${pgm}_${data}_${i}_out.txt
            errfile=out/${pgm}_${data}_${i}_err.txt
            rm -f $outfile $errfile
            echo "running ${pgm} ${data} ${i}"
            if [ "$pgm" = "TCraw" -o "$pgm" = "DBLPraw" -o "$pgm" = "Wineraw" ]; then
                if [ ! -d "data_pickle" ]; then
                    mkdir data_pickle
                fi
                # no processes, so don't bother giving -I thread
                timeout 1800 time python3 -m da -r --rule ORBtimer.da --data $data --mode raw 1>>${outfile} 2>>${errfile}
                # in case of timeout, append timeout message to outfile, to confirm that execution didn't abort for other reasons.
                if [ "$?" == "124" ]; then
                    echo "timeout!" >>$outfile
                fi
                if ! grep -q "dump_os_total" "$outfile"; then
                    echo "incomplete iteration; skipping remaining iterations"
                    break
                fi
            else
                # if removing -I thread, add:  --message-buffer-size=409600000
                timeout 1800 time python3 -m da -r -I thread --rule ORBtimer.da --bench $pgm --data $data 1>>${outfile} 2>>${errfile}
                if [ "$?" == "124" ]; then
                    echo "timeout!" >>$outfile
                fi
                if ! grep -q "total_os_total" "$outfile"; then
                    echo "incomplete iteration; skipping remaining iterations"
                    break
                elif [ "${i}" = "${startIter}" ]; then
                    latestanswers=`ls -t __pycache__/*.answers | head -n 1`
                    mv $latestanswers out/${pgm/_break/""}_${data}_da_answers.txt
                fi
            fi
        done
    done
done

for pgm in ${xsbPgms}; do
    # remove "xsb" suffix from pgm name to get name of .P file
    pgmfile=${pgm::-3}
    # datasets is needed by extract_timings
    if [ "${pgm::2}" = "TC" ]; then
        datasets="$tcdatasets"
    elif [ "${pgm::4}" = "DBLP" ]; then
        datasets="dblp"
    elif [ "${pgm::4}" = "Wine" ]; then
        datasets="wine"
    else
        echo "unknown xsb program $pgm"
        break
    fi
    for data in ${datasets}; do
        for ((i=${startIter};i<=${endIter};i++)); do
            outfile=out/${pgm}_${data}_${i}_out.txt
            errfile=out/${pgm}_${data}_${i}_err.txt
            rm -f $outfile $errfile xsb_result.txt
            # redirect stdout to a file to avoid clutter on the console, but it contains nothing interesting, so overwrite it with the result file.
            if [ "${pgm::2}" = "TC" ]; then
                echo "running ${pgm} ${data} ${i}"
                timeout 1800 time xsb -e "['$pgmfile'], test('data_raw/$data'), halt."  1>>${outfile} 2>>${errfile}
                if [ "$?" == "124" ]; then
                    echo "timeout!" >>tc_result.txt
                fi
                mv -f tc_result.txt $outfile
            elif [ "${pgm::4}" = "DBLP" ]; then
                echo "running ${pgm} ${i}"
                timeout 1800 time xsb -e "['$pgmfile'], test, halt."  1>>${outfile} 2>>${errfile}
                if [ "$?" == "124" ]; then
                    echo "timeout!" >>dblp_result.txt
                fi
                mv -f dblp_result.txt $outfile
            elif [ "${pgm::4}" = "Wine" ]; then
                echo "running ${pgm} ${i}"
                timeout 1800 time xsb -e "['$pgmfile'], test, halt."  1>>${outfile} 2>>${errfile}
                if [ "$?" == "124" ]; then
                    echo "timeout!" >>wine_result.txt
                fi
                mv -f wine_result.txt $outfile
            else
                echo "unknown program $pgm"
                break
            fi
            if ! grep -q "computing cputime" "$outfile"; then
                echo "incomplete iteration; skipping remaining iterations"
                break
            elif [ "${i}" = "${startIter}" -a ${pgm:-4} == "Wxsb" ]; then 
                latestanswers=`ls -t *answers.txt | head -n 1`
                mv $latestanswers out/${pgm::-4}_${data}_xsb_answers.txt
            fi
        done
    done
done

echo " =============== FINISHED ==================="
tput bel