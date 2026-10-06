`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: Raju Machupalli
// 
// Create Date: 06/01/2024 10:45:59 AM
// Design Name: 
// Module Name: multi
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////


// 7x8-bit multiplier 
module multi(
	input wire [6:0] a,
	input wire [7:0] b,
	output wire [14:0] c
	);
	
	assign c = a * b;
endmodule
