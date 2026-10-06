# Ramyad: All the tests are commented because they access internal signals and it will fail
#   on tt cocotb automation.
# They are separated by obvious comment lines, and some of even the code in the comments.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge



@cocotb.test()
async def test_obvious(dut):
    assert 2 > 1, "Testing the obvious"

# ----------------------------------------------------------------------------
# ----------------------Single MAC TEST---------------------------------------
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
''' Single MAC TEST
Ramyad: Lol, finished within 2hrs!

Testing MAC unit with a vanilla instantiated block as this in the main module:

    // Declare the necessary signals for the MAC module
    wire [7:0] mac_in;
    wire mac_en_wr_w;
    wire mac_en_wr_a;
    wire [15:0] mac_out;

    // Instantiate the MAC module
    MAC #(8) u_mac (
        .clk(clk),
        .rst(rst),
        .in(mac_in),
        .en_wr_w(mac_en_wr_w),
        .en_wr_a(mac_en_wr_a),
        .out(mac_out)
    );

    // Example connections (you'll need to set these appropriately based on your design requirements)
    assign mac_in = ui_in;        // Connect ui_in to mac_in (example)
    assign mac_en_wr_w = ena;     // Connect ena to mac_en_wr_w (example)
    assign mac_en_wr_a = ena;     // Connect ena to mac_en_wr_a (example)

'''
'''
@cocotb.test()
async def test_MAC_rst(dut):

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset the device
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)  # Hold reset for 5 clock cycles
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)  # Wait for a few clock cycles after reset

    assert int(dut.myCIM.u_mac.w.value) == 0
    assert int(dut.myCIM.u_mac.a.value) == 0

@cocotb.test()
async def test_MAC_internal_value_write_and_mult_and_rst(dut):

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset the device
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)  # Hold reset for 5 clock cycles
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)  # Wait for a few clock cycles after reset

    dut.myCIM.mac_en_wr_w.value = 1
    dut.myCIM.mac_in.value = 8

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    internal_value = int(dut.myCIM.u_mac.w.value)
    assert int(dut.myCIM.u_mac.w.value) == 8, f"Expected {8}, found {internal_value}"

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    dut.myCIM.mac_en_wr_w.value = 0
    dut.myCIM.mac_en_wr_a.value = 1
    dut.myCIM.mac_in.value = 10

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    internal_value = int(dut.myCIM.u_mac.w.value)
    assert int(dut.myCIM.u_mac.a.value) == 10, f"Expected {10}, found {internal_value}"

    assert int(dut.myCIM.u_mac.out.value) == 80, f"Expected {80}, found {internal_value}"
    assert int(dut.myCIM.mac_out.value) == 80, f"Expected {80}, found {internal_value}"

    dut.myCIM.mac_en_wr_a.value = 0

    # Reset the device
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)  # Hold reset for 5 clock cycles
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)  # Wait for a few clock cycles after reset

    assert int(dut.myCIM.u_mac.w.value) == 0
    assert int(dut.myCIM.u_mac.a.value) == 0
'''

# ----------------------------------------------------------------------------
# ------------------------Multiple MAC loading w and a------------------------
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------

''' Multiple MAC loading w and a
Ramyad: Wow, this logic and test worked within 2hrs! 2x2hrs for now.

Tested this peice of code:

`default_nettype none

module tt_um_8bit_vector_compute_in_SRAM (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);
    wire rst = !rst_n;

    // Use IO as I
    assign uio_oe  = 0;
    assign uio_out = 0;

    // output
    reg [7:0] data_out;
    assign uo_out = data_out;

    // inputs
    wire [1:0] op = ui_in[7:6];           // op code or control
    wire [5:0] address = ui_in[5:0];      // MAC unit address
    wire [7:0] data_in = uio_in[7:0];          // Data in for loading

    // MACs
    wire [7:0]  mac_in[0:7];
    reg         mac_en_wr_w[0:7];
    reg         mac_en_wr_a[0:7];
    wire [15:0] mac_out[0:7];

    // Assigning outside genvar, not sure why cocotb throws an error if inside
    assign mac_in[0] = data_in;
    assign mac_in[1] = data_in;
    assign mac_in[2] = data_in;
    assign mac_in[3] = data_in;
    assign mac_in[4] = data_in;
    assign mac_in[5] = data_in;
    assign mac_in[6] = data_in;
    assign mac_in[7] = data_in;

    // Instantiate 8 MAC modules using a generate block
    genvar i;
    generate
        for (i = 0; i < 8; i = i + 1) begin : mac_gen
            MAC u_mac (
                .clk(clk),
                .rst(rst),
                .in(mac_in[i]),
                .en_wr_w(mac_en_wr_w[i]),
                .en_wr_a(mac_en_wr_a[i]),
                .out(mac_out[i])
            );
        end
    endgenerate

    always @(*) begin
        // Default values
        integer j;
        for (j = 0; j < 8; j = j + 1) begin
            mac_en_wr_w[j] = 0;
            mac_en_wr_a[j] = 0;
        end

        case (op)
            2'b00: begin
                if (address < 8) begin
                    mac_en_wr_w[address] = 1;
                end
            end
            2'b01: begin
                if (address < 8) begin
                    mac_en_wr_a[address] = 1;
                end
            end
            default: begin
                // Do nothing for other op codes
            end
        endcase
    end

endmodule


// MAC -------------------------------------------------------------
module MAC #(
    parameter BIT_WIDTH = 8
)(
    input                           clk,
    input                           rst,
    input   wire  [BIT_WIDTH-1:0]   in,
    input   wire                    en_wr_w,
    input   wire                    en_wr_a,

    output  reg   [BIT_WIDTH*2-1:0] out
);

    reg [BIT_WIDTH-1:0] w;
    reg [BIT_WIDTH-1:0] a;

    always @(posedge clk or posedge rst) begin
        if(rst) begin
            w <= {BIT_WIDTH{1'b0}};
            a <= {BIT_WIDTH{1'b0}};
        end
        else if (en_wr_w) begin
            w <= in;
        end
        else if (en_wr_a) begin
            a <= in;
        end
    end

    always @(*) begin
        out = a * w;
    end


    endmodule
'''
'''
@cocotb.test()
async def test_MAC_write_w_a_with_op(dut):
    # Start the clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset the device
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)  # Hold reset for 5 clock cycles
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)  # Wait for a few clock cycles after reset

    # Function to write a weight to a specified MAC
    async def write_weight(mac_address, weight):
        # Set the op code to 00 (write weight) and address
        dut.ui_in.value = (0b00 << 6) | mac_address
        # Set the weight data
        dut.uio_in.value = weight
        # Wait for a clock cycle to simulate the write
        await ClockCycles(dut.clk, 1)

    # Function to write a value to 'a' register of a specified MAC
    async def write_act(mac_address, a_value):
        # Set the op code to 01 (write a value) and address
        dut.ui_in.value = (0b01 << 6) | mac_address
        # Set the a value data
        dut.uio_in.value = a_value
        # Wait for a clock cycle to simulate the write
        await ClockCycles(dut.clk, 1)

    # Test data
    weights = [10, 20, 30, 40, 50, 60, 70, 80]  # Weights for each MAC
    a_values = [5, 15, 25, 35, 45, 55, 65, 75]  # 'a' values for each MAC

    # Iterate over all MAC addresses and write the weights and 'a' values
    for mac_address in range(8):
        await write_weight(mac_address, weights[mac_address])
        await write_act(mac_address, a_values[mac_address])

    # Wait for a few clock cycles to ensure the writes are complete
    await ClockCycles(dut.clk, 10)

    # Check the internal values of w and a for all MACs
    for mac_address in range(8):
        mac_w = int(dut.myCIM.mac_gen[mac_address].u_mac.w.value)
        mac_a = int(dut.myCIM.mac_gen[mac_address].u_mac.a.value)
        mac_out = int(dut.myCIM.mac_gen[mac_address].u_mac.out.value)

        expected_out = weights[mac_address] * a_values[mac_address]

        assert mac_w == weights[mac_address], f"MAC {mac_address} w mismatch: {mac_w} != {weights[mac_address]}"
        assert mac_a == a_values[mac_address], f"MAC {mac_address} a mismatch: {mac_a} != {a_values[mac_address]}"
        assert mac_out == expected_out, f"MAC {mac_address} out mismatch: {mac_out} != {expected_out}"
'''
# ----------------------------------------------------------------------------
# --------------------Adder Tree Tests----------------------------------------
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
''' Testing Adder Tree
Ramyad: Done in a hour?! Total time 5hrs
Everything works apparently, did test MOST things...

`default_nettype none

module tt_um_8bit_vector_compute_in_SRAM (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);
    wire rst = !rst_n;

    // Use IO as I
    assign uio_oe  = 0;
    assign uio_out = 0;

    // output
    reg [7:0] data_out;
    assign uo_out = data_out;

    // inputs
    wire [1:0] op = ui_in[7:6];           // op code or control
    wire [5:0] address = ui_in[5:0];      // MAC unit address
    wire [7:0] data_in = uio_in[7:0];          // Data in for loading

    // MACs
    wire [7:0]  mac_in[0:7];
    reg         mac_en_wr_w[0:7];
    reg         mac_en_wr_a[0:7];
    wire [15:0] mac_out[0:7];

    // Assigning outside genvar, not sure why cocotb throws an error if inside
    assign mac_in[0] = data_in;
    assign mac_in[1] = data_in;
    assign mac_in[2] = data_in;
    assign mac_in[3] = data_in;
    assign mac_in[4] = data_in;
    assign mac_in[5] = data_in;
    assign mac_in[6] = data_in;
    assign mac_in[7] = data_in;

    // Instantiate 8 MAC modules using a generate block
    genvar i;
    generate
        for (i = 0; i < 8; i = i + 1) begin : mac_gen
            MAC u_mac (
                .clk(clk),
                .rst(rst),
                .in(mac_in[i]),
                .en_wr_w(mac_en_wr_w[i]),
                .en_wr_a(mac_en_wr_a[i]),
                .out(mac_out[i])
            );
        end
    endgenerate

    // Adder Tree Level 1
    wire [15:0] l1_0_s;
    wire        l1_0_c;
    wire [15:0] l1_1_s;
    wire        l1_1_c;
    wire [15:0] l1_2_s;
    wire        l1_2_c;
    wire [15:0] l1_3_s;
    wire        l1_3_c;

    cla #(16) adder_l1_0 (
            .a_in(mac_out[0]),
            .b_in(mac_out[1]),
            .c_in(1'b0),
            .s_out(l1_0_s),
            .c_out(l1_0_c)
        );

    cla #(16) adder_l1_1 (
            .a_in(mac_out[2]),
            .b_in(mac_out[3]),
            .c_in(1'b0),
            .s_out(l1_1_s),
            .c_out(l1_1_c)
        );

    cla #(16) adder_l1_2 (
            .a_in(mac_out[4]),
            .b_in(mac_out[5]),
            .c_in(1'b0),
            .s_out(l1_2_s),
            .c_out(l1_2_c)
        );

    cla #(16) adder_l1_3 (
            .a_in(mac_out[6]),
            .b_in(mac_out[7]),
            .c_in(1'b0),
            .s_out(l1_3_s),
            .c_out(l1_3_c)
        );


    // Adder Tree Level 2
    wire [16:0] l2_0_s;
    wire        l2_0_c;
    wire [16:0] l2_1_s;
    wire        l2_1_c;

    cla #(17) adder_l2_0 (
            .a_in({l1_0_c, l1_0_s}),
            .b_in({l1_1_c, l1_1_s}),
            .c_in(1'b0),
            .s_out(l2_0_s),
            .c_out(l2_0_c)
        );

    cla #(17) adder_l2_1 (
            .a_in({l1_2_c, l1_2_s}),
            .b_in({l1_3_c, l1_3_s}),
            .c_in(1'b0),
            .s_out(l2_1_s),
            .c_out(l2_1_c)
        );

    // Adder Tree Level 3
    wire [17:0] l3_0_s;
    wire        l3_0_c;

    cla #(18) adder_l3_0 (
        .a_in({l2_0_c, l2_0_s}),
        .b_in({l2_1_c, l2_1_s}),
        .c_in(1'b0),
        .s_out(l3_0_s),
        .c_out(l3_0_c)
    );

    wire [18:0] s_adder_tree =  {l3_0_c, l3_0_s};



    // Control & Op
    always @(*) begin
        // Default values
        integer j;
        for (j = 0; j < 8; j = j + 1) begin
            mac_en_wr_w[j] = 0;
            mac_en_wr_a[j] = 0;
        end

        case (op)
            2'b00: begin
                if (address < 8) begin
                    mac_en_wr_w[address] = 1;
                end
            end
            2'b01: begin
                if (address < 8) begin
                    mac_en_wr_a[address] = 1;
                end
            end
            default: begin
                // Do nothing for other op codes
            end
        endcase
    end

endmodule


// MAC -------------------------------------------------------------
module MAC #(
    parameter BIT_WIDTH = 8
)(
    input                           clk,
    input                           rst,
    input   wire  [BIT_WIDTH-1:0]   in,
    input   wire                    en_wr_w,
    input   wire                    en_wr_a,

    output  reg   [BIT_WIDTH*2-1:0] out
);

    reg [BIT_WIDTH-1:0] w;
    reg [BIT_WIDTH-1:0] a;

    always @(posedge clk or posedge rst) begin
        if(rst) begin
            w <= {BIT_WIDTH{1'b0}};
            a <= {BIT_WIDTH{1'b0}};
        end
        else if (en_wr_w) begin
            w <= in;
        end
        else if (en_wr_a) begin
            a <= in;
        end
    end

    always @(*) begin
        out = a * w;
    end


    endmodule


// Adder Carry Look ahead from https://github.com/Hammersamatom/cla
// must verify, it says it verfied till 32 bits
module cla #(
    parameter BITS = 16
)(
    input wire [BITS - 1:0] a_in,
    input wire [BITS - 1:0] b_in,
    input wire c_in,
    output wire [BITS - 1:0] s_out,
    output wire c_out
);
    // Propagate / Generate
    wire [BITS - 1:0] w_prop;
    assign w_prop[BITS - 1:0] = a_in[BITS - 1:0] ^ b_in[BITS - 1:0];

    wire [BITS - 1:0] w_gen;
    assign w_gen[BITS - 1:0] = a_in[BITS - 1:0] & b_in[BITS - 1:0];

    wire [BITS:0] w_carry;

    assign w_carry[0] = c_in; // Sets w_carry[0] = c_in

    // Carry Lookahead Unit
    genvar carryBitIndex;
    generate
        for (carryBitIndex = 1; carryBitIndex <= BITS; carryBitIndex = carryBitIndex + 1)
        begin
            wire [carryBitIndex:0] components;

            assign components[0] = w_gen[carryBitIndex - 1];

            genvar i;
            for (i = 1; i < carryBitIndex; i = i + 1)
            begin
                assign components[i] = w_gen[carryBitIndex - i - 1] & &w_prop[carryBitIndex - 1 : carryBitIndex - i];
            end
            assign components[carryBitIndex] = w_carry[0] & &w_prop[carryBitIndex - 1:0];


            assign w_carry[carryBitIndex] = |components;

        end
    endgenerate

    // Assigning outputs
    assign s_out[BITS - 1:0] = w_prop[BITS - 1:0] ^ w_carry[BITS - 1:0];
    assign c_out = w_carry[BITS];

    endmodule
'''
'''
@cocotb.test()
async def test_adder_tree_levels(dut):
    # Start the clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset the device
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)  # Hold reset for 5 clock cycles
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)  # Wait for a few clock cycles after reset

    # Function to write a weight to a specified MAC
    async def write_weight(mac_address, weight):
        # Set the op code to 00 (write weight) and address
        dut.ui_in.value = (0b00 << 6) | mac_address
        # Set the weight data
        dut.uio_in.value = weight
        # Wait for a clock cycle to simulate the write
        await ClockCycles(dut.clk, 1)

    # Function to write a value to 'a' register of a specified MAC
    async def write_act(mac_address, a_value):
        # Set the op code to 01 (write a value) and address
        dut.ui_in.value = (0b01 << 6) | mac_address
        # Set the a value data
        dut.uio_in.value = a_value
        # Wait for a clock cycle to simulate the write
        await ClockCycles(dut.clk, 1)

    # Test data
    weights = [10, 20, 30, 40, 50, 60, 70, 80]  # Weights for each MAC
    a_values = [5, 15, 25, 35, 45, 55, 65, 75]  # 'a' values for each MAC

    # Iterate over all MAC addresses and write the weights and 'a' values
    for mac_address in range(8):
        await write_weight(mac_address, weights[mac_address])
        await write_act(mac_address, a_values[mac_address])

    # Wait for a few clock cycles to ensure the writes are complete
    await ClockCycles(dut.clk, 10)

    # Check the internal values of w and a for all MACs
    for mac_address in range(8):
        mac_w = int(dut.myCIM.mac_gen[mac_address].u_mac.w.value)
        mac_a = int(dut.myCIM.mac_gen[mac_address].u_mac.a.value)
        mac_out = int(dut.myCIM.mac_gen[mac_address].u_mac.out.value)

        expected_out = weights[mac_address] * a_values[mac_address]

        assert mac_w == weights[mac_address], f"MAC {mac_address} w mismatch: {mac_w} != {weights[mac_address]}"
        assert mac_a == a_values[mac_address], f"MAC {mac_address} a mismatch: {mac_a} != {a_values[mac_address]}"
        assert mac_out == expected_out, f"MAC {mac_address} out mismatch: {mac_out} != {expected_out}"

    # Check adder tree level 1 outputs
    # Adder l1_0
    l1_0_s = int(dut.myCIM.l1_0_s.value)
    l1_0_c = int(dut.myCIM.l1_0_c.value)
    expected_sum = (weights[0] * a_values[0]) + (weights[1] * a_values[1])
    expected_carry = ((weights[0] * a_values[0]) + (weights[1] * a_values[1])) >> 16
    assert l1_0_s == (expected_sum & 0xFFFF), f"l1_0_s mismatch: {l1_0_s} != {expected_sum & 0xFFFF}"
    assert l1_0_c == (expected_carry & 0x1), f"l1_0_c mismatch: {l1_0_c} != {expected_carry & 0x1}"

    # Adder l1_1
    l1_1_s = int(dut.myCIM.l1_1_s.value)
    l1_1_c = int(dut.myCIM.l1_1_c.value)
    expected_sum = (weights[2] * a_values[2]) + (weights[3] * a_values[3])
    expected_carry = ((weights[2] * a_values[2]) + (weights[3] * a_values[3])) >> 16
    assert l1_1_s == (expected_sum & 0xFFFF), f"l1_1_s mismatch: {l1_1_s} != {expected_sum & 0xFFFF}"
    assert l1_1_c == (expected_carry & 0x1), f"l1_1_c mismatch: {l1_1_c} != {expected_carry & 0x1}"

    # Adder l1_2
    l1_2_s = int(dut.myCIM.l1_2_s.value)
    l1_2_c = int(dut.myCIM.l1_2_c.value)
    expected_sum = (weights[4] * a_values[4]) + (weights[5] * a_values[5])
    expected_carry = ((weights[4] * a_values[4]) + (weights[5] * a_values[5])) >> 16
    assert l1_2_s == (expected_sum & 0xFFFF), f"l1_2_s mismatch: {l1_2_s} != {expected_sum & 0xFFFF}"
    assert l1_2_c == (expected_carry & 0x1), f"l1_2_c mismatch: {l1_2_c} != {expected_carry & 0x1}"

    # Adder l1_3
    l1_3_s = int(dut.myCIM.l1_3_s.value)
    l1_3_c = int(dut.myCIM.l1_3_c.value)
    expected_sum = (weights[6] * a_values[6]) + (weights[7] * a_values[7])
    expected_carry = ((weights[6] * a_values[6]) + (weights[7] * a_values[7])) >> 16
    assert l1_3_s == (expected_sum & 0xFFFF), f"l1_3_s mismatch: {l1_3_s} != {expected_sum & 0xFFFF}"
    assert l1_3_c == (expected_carry & 0x1), f"l1_3_c mismatch: {l1_3_c} != {expected_carry & 0x1}"

    # Check adder tree level 2 outputs
    # Adder l2_0
    l2_0_s = int(dut.myCIM.l2_0_s.value)
    l2_0_c = int(dut.myCIM.l2_0_c.value)
    expected_sum = (int(dut.myCIM.l1_0_c.value) << 16 | int(dut.myCIM.l1_0_s.value)) + \
                   (int(dut.myCIM.l1_1_c.value) << 16 | int(dut.myCIM.l1_1_s.value))
    expected_carry = (expected_sum >> 17) & 0x1
    expected_sum = expected_sum & 0x1FFFF
    assert l2_0_s == expected_sum, f"l2_0_s mismatch: {l2_0_s} != {expected_sum}"
    assert l2_0_c == expected_carry, f"l2_0_c mismatch: {l2_0_c} != {expected_carry}"

    # Adder l2_1
    l2_1_s = int(dut.myCIM.l2_1_s.value)
    l2_1_c = int(dut.myCIM.l2_1_c.value)
    expected_sum = (int(dut.myCIM.l1_2_c.value) << 16 | int(dut.myCIM.l1_2_s.value)) + \
                   (int(dut.myCIM.l1_3_c.value) << 16 | int(dut.myCIM.l1_3_s.value))
    expected_carry = (expected_sum >> 17) & 0x1
    expected_sum = expected_sum & 0x1FFFF
    assert l2_1_s == expected_sum, f"l2_1_s mismatch: {l2_1_s} != {expected_sum}"
    assert l2_1_c == expected_carry, f"l2_1_c mismatch: {l2_1_c} != {expected_carry}"

    # Check adder tree level 3 outputs
    l3_0_s = int(dut.myCIM.l3_0_s.value)
    l3_0_c = int(dut.myCIM.l3_0_c.value)
    expected_sum = (int(dut.myCIM.l2_0_c.value) << 17 | int(dut.myCIM.l2_0_s.value)) + \
                   (int(dut.myCIM.l2_1_c.value) << 17 | int(dut.myCIM.l2_1_s.value))
    expected_carry = (expected_sum >> 18) & 0x1
    expected_sum = expected_sum & 0x3FFFF
    assert l3_0_s == expected_sum, f"l3_0_s mismatch: {l3_0_s} != {expected_sum}"
    assert l3_0_c == expected_carry, f"l3_0_c mismatch: {l3_0_c} != {expected_carry}"

    # Check the final adder tree output
    s_adder_tree = int(dut.myCIM.s_adder_tree.value)
    expected_s_adder_tree = (expected_carry << 18) | expected_sum
    assert s_adder_tree == expected_s_adder_tree, f"s_adder_tree mismatch: {s_adder_tree} != {expected_s_adder_tree}"

@cocotb.test()
async def test_adder_tree(dut):
    # Start the clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset the device
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)  # Hold reset for 5 clock cycles
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)  # Wait for a few clock cycles after reset

    # Function to write a weight to a specified MAC
    async def write_weight(mac_address, weight):
        # Set the op code to 00 (write weight) and address
        dut.ui_in.value = (0b00 << 6) | mac_address
        # Set the weight data
        dut.uio_in.value = weight
        # Wait for a clock cycle to simulate the write
        await ClockCycles(dut.clk, 1)

    # Function to write a value to 'a' register of a specified MAC
    async def write_act(mac_address, a_value):
        # Set the op code to 01 (write a value) and address
        dut.ui_in.value = (0b01 << 6) | mac_address
        # Set the a value data
        dut.uio_in.value = a_value
        # Wait for a clock cycle to simulate the write
        await ClockCycles(dut.clk, 1)

    # Test vectors for weights and a values
    test_vectors = [
        ([10, 20, 30, 40, 50, 60, 70, 80], [5, 15, 25, 35, 45, 55, 65, 75]),
        ([255, 255, 255, 255, 255, 255, 255, 255], [1, 1, 1, 1, 1, 1, 1, 1]),
        ([0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0]),
        ([1, 2, 3, 4, 5, 6, 7, 8], [8, 7, 6, 5, 4, 3, 2, 1]),
        ([255, 255, 255, 255, 255, 255, 255, 255], [255, 255, 255, 255, 255, 255, 255, 255]),
        ([255, 0, 255, 0, 255, 0, 255, 0], [0, 255, 0, 255, 0, 255, 0, 255]),
        ([128, 64, 32, 16, 8, 4, 2, 1], [1, 2, 4, 8, 16, 32, 64, 128]),
        ([1, 1, 1, 1, 1, 1, 1, 1], [1, 2, 3, 4, 5, 6, 7, 8]),
        ([254, 253, 252, 251, 250, 249, 248, 247], [1, 2, 3, 4, 5, 6, 7, 8]),
        ([1, 2, 3, 4, 5, 6, 7, 8], [254, 253, 252, 251, 250, 249, 248, 247]),
        ([170, 85, 170, 85, 170, 85, 170, 85], [85, 170, 85, 170, 85, 170, 85, 170]),
        ([255, 127, 63, 31, 15, 7, 3, 1], [1, 3, 7, 15, 31, 63, 127, 255]),
        ([100, 150, 200, 250, 50, 100, 150, 200], [200, 150, 100, 50, 250, 200, 150, 100])
    ]

    for weights, a_values in test_vectors:
        # Iterate over all MAC addresses and write the weights and 'a' values
        for mac_address in range(8):
            await write_weight(mac_address, weights[mac_address])
            await write_act(mac_address, a_values[mac_address])

        # Wait for a few clock cycles to ensure the writes are complete
        await ClockCycles(dut.clk, 10)

        # Calculate the expected final result
        expected_s_adder_tree = sum(weights[i] * a_values[i] for i in range(8))

        # Check the final adder tree output
        s_adder_tree = int(dut.myCIM.s_adder_tree.value)
        assert s_adder_tree == expected_s_adder_tree, f"s_adder_tree mismatch: {s_adder_tree} != {expected_s_adder_tree}"
'''
# ----------------------------------------------------------------------------
# ---------------------------Read Result Test---------------------------------
# ----------------------------------------------------------------------------
'''
Took 2hrs to write an test. 7hr total to finish 8 macs.

// Ops
`define LOAD_W  2'b00
`define LOAD_A  2'b01
`define READ_S  2'b10
`define NOP     2'b11

`default_nettype none

module tt_um_8bit_vector_compute_in_SRAM (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);
    wire rst = !rst_n;

    // Use IO as I
    assign uio_oe  = 0;
    assign uio_out = 0;

    // output
    reg [7:0] data_out;
    assign uo_out = data_out;

    // inputs
    wire [1:0] op = ui_in[7:6];           // op code or control
    wire [5:0] address = ui_in[5:0];      // MAC unit address
    wire [7:0] data_in = uio_in[7:0];     // Data in for loading

    // MACs
    wire [7:0]  mac_in[0:7];
    reg         mac_en_wr_w[0:7];
    reg         mac_en_wr_a[0:7];
    wire [15:0] mac_out[0:7];

    // Assigning outside genvar, not sure why cocotb throws an error if inside
    assign mac_in[0] = data_in;
    assign mac_in[1] = data_in;
    assign mac_in[2] = data_in;
    assign mac_in[3] = data_in;
    assign mac_in[4] = data_in;
    assign mac_in[5] = data_in;
    assign mac_in[6] = data_in;
    assign mac_in[7] = data_in;

    // Instantiate 8 MAC modules
    genvar i;
    generate
        for (i = 0; i < 8; i = i + 1) begin : mac_gen
            MAC u_mac (
                .clk(clk),
                .rst(rst),
                .in(mac_in[i]),
                .en_wr_w(mac_en_wr_w[i]),
                .en_wr_a(mac_en_wr_a[i]),
                .out(mac_out[i])
            );
        end
    endgenerate

    // Adder Tree Level 1
    wire [15:0] l1_0_s;
    wire        l1_0_c;
    wire [15:0] l1_1_s;
    wire        l1_1_c;
    wire [15:0] l1_2_s;
    wire        l1_2_c;
    wire [15:0] l1_3_s;
    wire        l1_3_c;

    cla #(16) adder_l1_0 (
            .a_in(mac_out[0]),
            .b_in(mac_out[1]),
            .c_in(1'b0),
            .s_out(l1_0_s),
            .c_out(l1_0_c)
        );

    cla #(16) adder_l1_1 (
            .a_in(mac_out[2]),
            .b_in(mac_out[3]),
            .c_in(1'b0),
            .s_out(l1_1_s),
            .c_out(l1_1_c)
        );

    cla #(16) adder_l1_2 (
            .a_in(mac_out[4]),
            .b_in(mac_out[5]),
            .c_in(1'b0),
            .s_out(l1_2_s),
            .c_out(l1_2_c)
        );

    cla #(16) adder_l1_3 (
            .a_in(mac_out[6]),
            .b_in(mac_out[7]),
            .c_in(1'b0),
            .s_out(l1_3_s),
            .c_out(l1_3_c)
        );


    // Adder Tree Level 2
    wire [16:0] l2_0_s;
    wire        l2_0_c;
    wire [16:0] l2_1_s;
    wire        l2_1_c;

    cla #(17) adder_l2_0 (
            .a_in({l1_0_c, l1_0_s}),
            .b_in({l1_1_c, l1_1_s}),
            .c_in(1'b0),
            .s_out(l2_0_s),
            .c_out(l2_0_c)
        );

    cla #(17) adder_l2_1 (
            .a_in({l1_2_c, l1_2_s}),
            .b_in({l1_3_c, l1_3_s}),
            .c_in(1'b0),
            .s_out(l2_1_s),
            .c_out(l2_1_c)
        );

    // Adder Tree Level 3
    wire [17:0] l3_0_s;
    wire        l3_0_c;

    cla #(18) adder_l3_0 (
        .a_in({l2_0_c, l2_0_s}),
        .b_in({l2_1_c, l2_1_s}),
        .c_in(1'b0),
        .s_out(l3_0_s),
        .c_out(l3_0_c)
    );

    wire [18:0] s_adder_tree =  {l3_0_c, l3_0_s};
    reg cache_s_adder_tree_en;


    // Control & Op
    always @(*) begin
        // Default values
        integer j1;
        for (j1 = 0; j1 < 8; j1 = j1 + 1) begin
            mac_en_wr_w[j1] = 0;
            mac_en_wr_a[j1] = 0;
        end
        cache_s_adder_tree_en = 0;

        case (op)
            // Load MAC W
            `LOAD_W: begin
                if (address < 8) begin
                    mac_en_wr_w[address[2:0]] = 1;
                end
            end
            // Load MAC A
            `LOAD_A: begin
                if (address < 8) begin
                    mac_en_wr_a[address[2:0]] = 1;
                end
            end
            `READ_S: begin
                cache_s_adder_tree_en = 1;
            end
        endcase
    end

    reg [7:0] cached_s_adder_tree [0:2];

    reg out_en;
    reg [1:0] out_counter;

    always @(posedge clk or posedge rst) begin
        if(rst) begin
            integer j2;
            for (j2 = 0; j2 < 3; j2 = j2 + 1) begin
                cached_s_adder_tree[j2] <= 0;
            end
            out_counter <= 0;
            out_en <= 0;
            data_out <= 0;
        end
        else if (cache_s_adder_tree_en) begin
            cached_s_adder_tree[0] <= s_adder_tree[7:0];
            cached_s_adder_tree[1] <= s_adder_tree[15:8];
            cached_s_adder_tree[2] <= {5'b0000, s_adder_tree[18:16]};

            out_en <= 1;
            out_counter <= 2;
        end
        else if (out_en) begin
            data_out <= cached_s_adder_tree[out_counter];
            if (out_counter == 0) begin
                out_en <= 0;
            end else begin
                out_counter <= out_counter - 1;
            end
        end
    end

endmodule


// MAC -------------------------------------------------------------
module MAC #(
    parameter BIT_WIDTH = 8
)(
    input                           clk,
    input                           rst,
    input   wire  [BIT_WIDTH-1:0]   in,
    input   wire                    en_wr_w,
    input   wire                    en_wr_a,

    output  reg   [BIT_WIDTH*2-1:0] out
);

    reg [BIT_WIDTH-1:0] w;
    reg [BIT_WIDTH-1:0] a;

    always @(posedge clk or posedge rst) begin
        if(rst) begin
            w <= {BIT_WIDTH{1'b0}};
            a <= {BIT_WIDTH{1'b0}};
        end
        else if (en_wr_w) begin
            w <= in;
        end
        else if (en_wr_a) begin
            a <= in;
        end
    end

    always @(*) begin
        out = a * w;
    end


    endmodule


// Adder Carry Look ahead from https://github.com/Hammersamatom/cla
// Verfied until 32 bits
module cla #(
    parameter BITS = 16
)(
    input wire [BITS - 1:0] a_in,
    input wire [BITS - 1:0] b_in,
    input wire c_in,
    output wire [BITS - 1:0] s_out,
    output wire c_out
);
    // Propagate / Generate
    wire [BITS - 1:0] w_prop;
    assign w_prop[BITS - 1:0] = a_in[BITS - 1:0] ^ b_in[BITS - 1:0];

    wire [BITS - 1:0] w_gen;
    assign w_gen[BITS - 1:0] = a_in[BITS - 1:0] & b_in[BITS - 1:0];

    wire [BITS:0] w_carry;

    assign w_carry[0] = c_in; // Sets w_carry[0] = c_in

    // Carry Lookahead Unit
    genvar carryBitIndex;
    generate
        for (carryBitIndex = 1; carryBitIndex <= BITS; carryBitIndex = carryBitIndex + 1)
        begin
            wire [carryBitIndex:0] components;

            assign components[0] = w_gen[carryBitIndex - 1];

            genvar i;
            for (i = 1; i < carryBitIndex; i = i + 1)
            begin
                assign components[i] = w_gen[carryBitIndex - i - 1] & &w_prop[carryBitIndex - 1 : carryBitIndex - i];
            end
            assign components[carryBitIndex] = w_carry[0] & &w_prop[carryBitIndex - 1:0];


            assign w_carry[carryBitIndex] = |components;

        end
    endgenerate

    // Assigning outputs
    assign s_out[BITS - 1:0] = w_prop[BITS - 1:0] ^ w_carry[BITS - 1:0];
    assign c_out = w_carry[BITS];

    endmodule
'''
'''
@cocotb.test()
async def test_single_read_s(dut):
    # Start the clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset the device
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)  # Hold reset for 5 clock cycles
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)  # Wait for a few clock cycles after reset

    # Function to write a weight to a specified MAC
    async def write_weight(mac_address, weight):
        # Set the op code to 00 (write weight) and address
        dut.ui_in.value = (0b00 << 6) | mac_address
        # Set the weight data
        dut.uio_in.value = weight
        # Wait for a clock cycle to simulate the write
        await ClockCycles(dut.clk, 1)

    # Function to write a value to 'a' register of a specified MAC
    async def write_act(mac_address, a_value):
        # Set the op code to 01 (write a value) and address
        dut.ui_in.value = (0b01 << 6) | mac_address
        # Set the a value data
        dut.uio_in.value = a_value
        # Wait for a clock cycle to simulate the write
        await ClockCycles(dut.clk, 1)

    # Function to read the result of the adder tree
    async def read_s():
        # Set the op code to 10 (read s_adder_tree)
        dut.ui_in.value = 0b10 << 6
        await ClockCycles(dut.clk, 1)

        dut.ui_in.value = 0b11 << 6
        await ClockCycles(dut.clk, 1)

        result = 0
        for i in range(3):
            await RisingEdge(dut.clk)
            result = (result << 8) | int(dut.uo_out.value)
        return result

    # Test data for a single case
    weights = [10, 20, 30, 40, 50, 60, 70, 80]
    a_values = [5, 15, 25, 35, 45, 55, 65, 75]

    # Iterate over all MAC addresses and write the weights and 'a' values
    for mac_address in range(8):
        await write_weight(mac_address, weights[mac_address])
        await write_act(mac_address, a_values[mac_address])

    # Wait for a few clock cycles to ensure the writes are complete
    await ClockCycles(dut.clk, 10)

    # Calculate the expected final result
    expected_s_adder_tree = sum(weights[i] * a_values[i] for i in range(8))

    # Check the final adder tree output
    s_adder_tree = int(dut.myCIM.s_adder_tree.value)
    assert s_adder_tree == expected_s_adder_tree, f"s_adder_tree mismatch: {s_adder_tree} != {expected_s_adder_tree}"

    # Send READ_S command to read the s_adder_tree value
    result = await read_s()
    assert result == expected_s_adder_tree, f"s_adder_tree mismatch: {result} != {expected_s_adder_tree}"


@cocotb.test()
async def test_read_s(dut):
    # Start the clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset the device
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)  # Hold reset for 5 clock cycles
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)  # Wait for a few clock cycles after reset

    # Function to write a weight to a specified MAC
    async def write_weight(mac_address, weight):
        # Set the op code to 00 (write weight) and address
        dut.ui_in.value = (0b00 << 6) | mac_address
        # Set the weight data
        dut.uio_in.value = weight
        # Wait for a clock cycle to simulate the write
        await ClockCycles(dut.clk, 1)

    # Function to write a value to 'a' register of a specified MAC
    async def write_act(mac_address, a_value):
        # Set the op code to 01 (write a value) and address
        dut.ui_in.value = (0b01 << 6) | mac_address
        # Set the a value data
        dut.uio_in.value = a_value
        # Wait for a clock cycle to simulate the write
        await ClockCycles(dut.clk, 1)

    # Function to read the result of the adder tree
    async def read_s():
        # Set the op code to 10 (read s_adder_tree)
        dut.ui_in.value = 0b10 << 6

        # print(f"---cache_s_adder_tree_en 10: {int(dut.myCIM.cache_s_adder_tree_en.value)}")

        await ClockCycles(dut.clk, 1)

        dut.ui_in.value = 0b11 << 6
        # print(f"---cache_s_adder_tree_en 11: {int(dut.myCIM.cache_s_adder_tree_en.value)}")

        await ClockCycles(dut.clk, 1)

        result = 0
        for i in range(3):
            await RisingEdge(dut.clk)
            result = (result << 8) | int(dut.uo_out.value)
            # print (f"---uo_out: {int(dut.uo_out.value)}")
        return result


    # Test vectors for weights and a values
    test_vectors = [
        ([1, 1, 1, 1, 1, 1, 1, 1], [1, 1, 1, 1, 1, 1, 1, 1]),
        ([1, 1, 1, 1, 1, 1, 1, 1], [1, 2, 3, 4, 5, 6, 7, 8]),
        ([10, 20, 30, 40, 50, 60, 70, 80], [5, 15, 25, 35, 45, 55, 65, 75]),
        ([255, 255, 255, 255, 255, 255, 255, 255], [1, 1, 1, 1, 1, 1, 1, 1]),
        ([0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0]),
        ([1, 2, 3, 4, 5, 6, 7, 8], [8, 7, 6, 5, 4, 3, 2, 1]),
        ([255, 255, 255, 255, 255, 255, 255, 255], [255, 255, 255, 255, 255, 255, 255, 255]),
        ([255, 0, 255, 0, 255, 0, 255, 0], [0, 255, 0, 255, 0, 255, 0, 255]),
        ([128, 64, 32, 16, 8, 4, 2, 1], [1, 2, 4, 8, 16, 32, 64, 128]),
        ([254, 253, 252, 251, 250, 249, 248, 247], [1, 2, 3, 4, 5, 6, 7, 8]),
        ([1, 2, 3, 4, 5, 6, 7, 8], [254, 253, 252, 251, 250, 249, 248, 247]),
        ([170, 85, 170, 85, 170, 85, 170, 85], [85, 170, 85, 170, 85, 170, 85, 170]),
        ([255, 127, 63, 31, 15, 7, 3, 1], [1, 3, 7, 15, 31, 63, 127, 255]),
        ([100, 150, 200, 250, 50, 100, 150, 200], [200, 150, 100, 50, 250, 200, 150, 100])
    ]

    for weights, a_values in test_vectors:
        # Iterate over all MAC addresses and write the weights and 'a' values
        for mac_address in range(8):
            await write_weight(mac_address, weights[mac_address])
            await write_act(mac_address, a_values[mac_address])

        # Wait for a few clock cycles to ensure the writes are complete
        await ClockCycles(dut.clk, 10)

        # Calculate the expected final result
        expected_s_adder_tree = sum(weights[i] * a_values[i] for i in range(8))

        # Check the final adder tree output
        s_adder_tree = int(dut.myCIM.s_adder_tree.value)
        assert s_adder_tree == expected_s_adder_tree, f"s_adder_tree mismatch: {s_adder_tree} != {expected_s_adder_tree}"

        # Send READ_S command to read the s_adder_tree value
        result = await read_s()
        # print(f"result: {result}")
        # print(f"expected_s_adder_tree: {expected_s_adder_tree}")
        # print(f"s_adder_tree: {s_adder_tree}")
        # print(f"cached_s_adder_tree[0]: {int(dut.myCIM.cached_s_adder_tree[0].value)}")
        # print(f"cached_s_adder_tree[1]: {int(dut.myCIM.cached_s_adder_tree[1].value)}")
        # print(f"cached_s_adder_tree[2]: {int(dut.myCIM.cached_s_adder_tree[2].value)}")
        # print()

        # # Check the final adder tree output
        assert result == expected_s_adder_tree, f"s_adder_tree mismatch: {result} != {expected_s_adder_tree}"
'''
# ----------------------------------------------------------------------------
# ---------------------------Only Extranl Singnals Tests----------------------
# ----------------------------------------------------------------------------
@cocotb.test()
async def test_read_only_with_external(dut):
    # Start the clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset the device
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)  # Hold reset for 5 clock cycles
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)  # Wait for a few clock cycles after reset

    # Function to write a weight to a specified MAC
    async def write_weight(mac_address, weight):
        # Set the op code to 00 (write weight) and address
        dut.ui_in.value = (0b00 << 6) | mac_address
        # Set the weight data
        dut.uio_in.value = weight
        # Wait for a clock cycle to simulate the write
        await ClockCycles(dut.clk, 1)

    # Function to write a value to 'a' register of a specified MAC
    async def write_act(mac_address, a_value):
        # Set the op code to 01 (write a value) and address
        dut.ui_in.value = (0b01 << 6) | mac_address
        # Set the a value data
        dut.uio_in.value = a_value
        # Wait for a clock cycle to simulate the write
        await ClockCycles(dut.clk, 1)

    # Function to read the result of the adder tree
    async def read_s():
        # Set the op code to 10 (read s_adder_tree)
        dut.ui_in.value = 0b10 << 6
        await ClockCycles(dut.clk, 1)

        # Prepare to read out the result
        dut.ui_in.value = 0b11 << 6
        await ClockCycles(dut.clk, 1)

        result = 0
        for i in range(3):
            await RisingEdge(dut.clk)
            result = (result << 8) | int(dut.uo_out.value)
        return result

    # Test vectors for weights and a values
    test_vectors = [
        # Positive values
        ([1, 1, 1, 1, 1, 1, 1, 1], [1, 1, 1, 1, 1, 1, 1, 1]),
        ([1, 1, 1, 1, 1, 1, 1, 1], [1, 2, 3, 4, 5, 6, 7, 8]),
        ([10, 20, 30, 40, 50, 60, 70, 80], [5, 15, 25, 35, 45, 55, 65, 75]),
        ([255, 255, 255, 255, 255, 255, 255, 255], [1, 1, 1, 1, 1, 1, 1, 1]),
        ([0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0]),
        ([1, 2, 3, 4, 5, 6, 7, 8], [8, 7, 6, 5, 4, 3, 2, 1]),
        ([255, 255, 255, 255, 255, 255, 255, 255], [255, 255, 255, 255, 255, 255, 255, 255]),
        ([255, 0, 255, 0, 255, 0, 255, 0], [0, 255, 0, 255, 0, 255, 0, 255]),
        ([128, 64, 32, 16, 8, 4, 2, 1], [1, 2, 4, 8, 16, 32, 64, 128]),
        ([254, 253, 252, 251, 250, 249, 248, 247], [1, 2, 3, 4, 5, 6, 7, 8]),
        ([1, 2, 3, 4, 5, 6, 7, 8], [254, 253, 252, 251, 250, 249, 248, 247]),
        ([170, 85, 170, 85, 170, 85, 170, 85], [85, 170, 85, 170, 85, 170, 85, 170]),
        ([255, 127, 63, 31, 15, 7, 3, 1], [1, 3, 7, 15, 31, 63, 127, 255]),
        ([100, 150, 200, 250, 50, 100, 150, 200], [200, 150, 100, 50, 250, 200, 150, 100]),
        # Negative values (two's complement)
        ([255, 255, 255, 255, 255, 255, 255, 255], [255, 255, 255, 255, 255, 255, 255, 255]),  # All -1
        ([128, 128, 128, 128, 128, 128, 128, 128], [128, 128, 128, 128, 128, 128, 128, 128]),  # All -128
        ([128, 255, 128, 255, 128, 255, 128, 255], [255, 128, 255, 128, 255, 128, 255, 128]),  # Alternating -128 and -1
        ([200, 150, 100, 50, 250, 200, 150, 100], [56, 106, 156, 206, 6, 56, 106, 156])  # Mixed positive and negative values
    ]


    for weights, a_values in test_vectors:
        # Iterate over all MAC addresses and write the weights and 'a' values
        for mac_address in range(8):
            await write_weight(mac_address, weights[mac_address])
            await write_act(mac_address, a_values[mac_address])

        # Wait for a few clock cycles to ensure the writes are complete
        await ClockCycles(dut.clk, 10)

        # Send READ_S command to read the s_adder_tree value
        result = await read_s()

        # Calculate the expected final result
        expected_s_adder_tree = sum(weights[i] * a_values[i] for i in range(8))

        # Check the final adder tree output
        assert result == expected_s_adder_tree, f"s_adder_tree mismatch: {result} != {expected_s_adder_tree}"