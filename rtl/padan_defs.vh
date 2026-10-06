// Definisi bersama PADAN. Di-include di DALAM badan modul (tanpa include guard,
// supaya setiap modul mendapat salinan fungsinya sendiri).
//
// Bobot baris checksum berbobot: Cw_i = sum_j w(j) * T[j,i], dengan w(j) = j + 1
// (model/padan.py). Dipakai generator di template_mem dan pemeriksa di
// abft_check. Satu definisi menjamin keduanya selalu memakai bobot yang sama.
function [8:0] padan_weight;
    input [7:0] row;
    padan_weight = {1'b0, row} + 9'd1;
endfunction
