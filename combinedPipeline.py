"""
Robin Aguilar
Beliveau and Noble Labs, 08/2/2019
Dependencies: Jellyfish, Bedtools
Input: Fasta for region of interest, JF index of genome of interest
Output: A .bed file of the elevated kmer regions, a .fa of said regions,
and a DF containing information about all the probes generated in those
regions. 
"""

#import all functions/modules needed
import time
import io
import sys
import re
import csv
import argparse
from collections import defaultdict
from itertools import islice
from operator import itemgetter, attrgetter
import subprocess
import numpy as np
import pandas as pd
import glob
import os
import refactoredBlockparse as bp
from Bio.SeqUtils import MeltingTemp as mt
from Bio.Seq import Seq
from Bio.Alphabet import IUPAC
from Bio.SeqUtils import GC
from Bio import SeqIO
from itertools import groupby
from Bio.Alphabet import generic_dna, generic_protein
from scipy import signal
import time
from collections import OrderedDict
import collections

#declare a timer
start_time=time.time()

#write arguments so users can specify the commands they would like for each variable
userInput = argparse.ArgumentParser(description=\
        '%Requires a FASTA file as input. And Jellyfish Index file of genome '
        'single-entry or multi-lined FASTA files are supported.  Returns a dataframe which '
        'can be used for further parsing or optionally can be made into a  '
        '.bed file can be outputted instead if \'-b\' is flagged. Tm values '
        'are corrected for [Na+] and [formamide].')
requiredNamed = userInput.add_argument_group('required arguments')
requiredNamed.add_argument('-f', '--fasta_file', action='store', required=True,
                               help='The FASTA file to find probes in')
requiredNamed.add_argument('-j', '--jf_indexfile', action='store', required=True,
                               help='The jf file of a given genome')
requiredNamed.add_argument('-chr', '--chr_name', action='store', required=True,
                               help='Define the scaffold being queried')
userInput.add_argument('-s', '--span_length', action='store', default=3000,
                           type=int,
                           help='The length of the scanning window for kmer enriched regions; default is '
                                '3000')
userInput.add_argument('-t', '--threshold', action='store', default=10,
                           type=int,
                           help='The minimum number of counts that defines a kmer enriched region; default is '
                                '10')
userInput.add_argument('-c', '--composition_score', action='store', default=0.5,
                           type=float,
                           help='The minimum percentage of kmers that pass threshold in window; default is '
                                '0.5')
    
requiredNamed.add_argument('-schr', '--scaffold_fasta', action='store',required=True,
                           help='Used to generate fasta file of kmer rich regions; default is ')

#Import user-specified command line values.
args = userInput.parse_args()
test_fasta = args.fasta_file
scaffold_fasta=args.scaffold_fasta
index = args.jf_indexfile
chrom= args.chr_name
SPAN = args.span_length
THRESHOLD = args.threshold
COMPOSITION = args.composition_score
    
#the names of output files to be generated
chr_name_jf_out=chrom+"_jf_temp.txt"
bed_file=chrom + "_regions.bed"
out_fasta=chrom + "_regions.fa"

#a list for the regions and scaffold sequences 
name_list=[]
sequence_list=[]
zipped_list=[]

"""
Write a function that will run jellyfish and then will later remove the query file after the script is run to save memory
"""

#this function reads the jellyfish index file and the fasta sequence to query 
#subprocess is called on the query

def jf_query(jf_index,fa_query):
    query_file=subprocess.call(['jellyfish', 'query', jf_index, '-s', 
                     fa_query, '-o', chr_name_jf_out], stderr=None, shell=False)
    return chr_name_jf_out

"""
Write a function that will handle the jellyfish and fasta processing to find map repeat coordinates.
"""

#the jf query file from the jf_query function in addition to the fasta being queried is used in this function
def map_coords(fa_file,jf_file):
    fa_seq = list(SeqIO.parse(open(fa_file),'fasta'))
    for fasta in fa_seq:
        sequence=str(fasta.seq).lower()
        print(sequence)

    #will return the length in characters of the fasta-seq
    k_mer=[]
    count=[]
    with open(jf_file, "r") as jf:
        for line in jf:
            k_mer.append(line.replace(" ","\t").split()[0])
            count.append(line.replace(" ","\t").split()[1])
            
        print(count)
  
    success_list=[]
    for i in count:
        if int(i)>=THRESHOLD:
            success_list.append(1)
        else:
            success_list.append(0)
            
    print(success_list)
    
    #make a list that will store the indices of each k-mer count
    indexList = []
    for i in range(0, (len(count))):
        indexList.append(i)
    print(indexList)
    
    #Contain an array of where all the successes are located
    iter_data = np.array(success_list)
    print(len(iter_data))

    #iterate through each of the successes in a sum fashion
    iter_vals_convolve=np.convolve(iter_data,np.ones(SPAN,dtype=int),'valid')
    print(len(iter_vals_convolve))
    
    iter_list=[]
    [iter_list.append(float(element)) for element in iter_vals_convolve]
    
    iterative_sum=pd.DataFrame(list(iter_list),columns=['iter_sum'])
    
    iterative_sum['row_span_start']=np.arange(len(iterative_sum))
    
    iterative_sum['row_span_end']=iterative_sum['row_span_start']+SPAN-1

    print(iterative_sum)
    
    passing_range_iter = iterative_sum.loc[(iterative_sum['iter_sum']/SPAN>=COMPOSITION)]
    
    print(passing_range_iter)

    #make two lists to take the min ranges and max ranges
    min_ranges=[]
    max_ranges=[]
    
    #write a loop that will split the dataframe into continuous chunks 
    for k,g in passing_range_iter.groupby(passing_range_iter['row_span_start'] - np.arange(passing_range_iter.shape[0])):
            min_ranges.append(min(g['row_span_start']) + START)
            max_ranges.append(max(g['row_span_end'])+len(k_mer[0]) + START)

    #add these two values into an dataframe where we can scan the indices of jellyfishmcount
    nucleotide_range = pd.DataFrame(list(zip(min_ranges, max_ranges)), columns =['start', 'end'])
    print(nucleotide_range)

    #let's add a column to the dataframe that will contain the chromosome information
    nucleotide_range['chr']=chrom

    #let's now merge by the chromosome to collapse overlapping regions
    collapsed_nucleotide_range=nucleotide_range.groupby((nucleotide_range.end.shift() - nucleotide_range.start).lt(0).cumsum()).agg(
        {'start': 'first','chr': 'first', 'end': 'last'})

    #collapsed_nucleotide_range.columns=["chr","start","end"]
    collapsed_nucleotide_range=collapsed_nucleotide_range[["chr","start","end"]]

    #then clean everything and have it run as 
    print(collapsed_nucleotide_range)
    collapsed_nucleotide_range.to_csv(bed_file, header=None, index=None, sep='\t')

    #call bedtools to generate a fasta from the sequence you have generated
    subprocess.call(['bedtools', 'getfasta', '-fi', scaffold_fasta, '-bed', bed_file, '-fo', out_fasta], stderr=None, shell=False)

    return out_fasta

"""
Write a function that will now run blockParse as a module to output the df of probes designed against the regions.
"""

#this function takes the fasta that you returned from the last function
def blockParse_run(output_fasta):
    fasta_sequences = list(SeqIO.parse(open(output_fasta),'fasta'))
    #you want to parse each fasta sequence as a string and append to a sequence list
    for fasta in fasta_sequences:
        name_list.append(fasta.id)
        sequence=(str(fasta.seq))
        sequence_list.append(sequence)
    #zip the names (headers of the fasta) and the string sequence into a list, then make into a dict
    zipped_list=zip(name_list,sequence_list)
    dict_name_seq=dict(zipped_list)
    #then run each item in the dict into the refactored blockParse script which can now handle multi-lined fastas
    for names,sequences in dict_name_seq.items():   
        print(bp.runSequenceCrawler(sequences,names, 36, 41, 20, 80,mt.DNA_NN3, 
                                      42, 47, 'AAAAA,TTTTT,CCCCC,GGGGG', 390, 50, 0,25, 
                                      25, None, True ,False, False,True, False, False))
            

def main():    
    
    returned_jf_file = jf_query(index,test_fasta)  
    
    mapped_fasta=map_coords(test_fasta,returned_jf_file)
    
    blockParse_run(mapped_fasta)
    
    print("---%s seconds ---"%(time.time()-start_time))
    #map_coords(test_fasta,test_bed)
    
    print("Done")
    
if __name__== "__main__":
    main()


