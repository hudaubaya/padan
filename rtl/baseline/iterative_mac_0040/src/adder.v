`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: Raju Machupalli
// 
// Create Date: 06/01/2024 10:47:37 AM
// Design Name: 
// Module Name: adder
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

// 32 bit adder
module adder (
	input wire [31:0] a,
	input wire [31:0] b,
	output wire [31:0] c
	);
	
	assign c = a + b;
endmodule
